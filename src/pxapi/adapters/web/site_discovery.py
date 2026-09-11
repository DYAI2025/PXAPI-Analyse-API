"""Discovers one public site's page population over static HTTP, inside one origin.

This is the static-HTTP implementation of ``SiteDiscoveryPort``. It reports what it observed and
what became of every source it tried; it decides nothing about what a page *is* or whether it
is selected, because those are Pixelkiez methodology and live on the other side of the port.

**The origin is established once, safely, and then never left.** The bootstrap reads the root of
the submitted target through ``SafePageFetcher`` under the product's ``PublicTargetPolicy`` —
every redirect hop re-validated and re-resolved, credentials refused, every private, loopback,
link-local and metadata address refused — and the origin of the response that finally arrived
becomes the canonical target origin. Every later fetch is made through a fetcher *scoped* to
that origin, so a robots file, a sitemap or a sitemap child that redirects anywhere else is
refused before its host is resolved or connected to. There is exactly one safety authority; the
scope only narrows it.

**Sources are bounded, and every bound is ours.** One seed request, one ``/robots.txt``, and at
most a declared number of sitemap documents and entries, all under one deadline spanning the
run. Links are read from the seed document only — this slice discovers a population and does
not fetch it, which is PXAPI-20's job. Reaching any bound is reported as ``BUDGET_EXHAUSTED`` or
``TIMEOUT``, which are facts about this analysis.

**robots.txt is read for ``Sitemap:`` and for nothing else.** No ``User-agent``, ``Allow``,
``Disallow`` or ``Crawl-delay`` directive is read, applied or claimed: this slice implements no
crawler policy, and a reader that parsed those lines would invite the assumption that it does.

**Every outcome is neutral.** An absent robots file, a sitemap that will not parse, a refusal, a
failure and a timeout are each reported in the contract's closed vocabulary, and none of them
is a statement about the website.

Standard library only; this adapter imports no third-party distribution.
"""

from __future__ import annotations

import re
import time
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urljoin
from xml.etree.ElementTree import ParseError, XMLPullParser

from pxapi.adapters.web.html_links import read_links
from pxapi.adapters.web.html_observations import decode_body
from pxapi.adapters.web.page_fetcher import SafePageFetcher
from pxapi.adapters.web.target_policy import PublicTargetPolicy
from pxapi.config.discovery_limits import DEFAULT_DISCOVERY_LIMITS, DiscoveryLimits
from pxapi.config.fetch_limits import DEFAULT_FETCH_LIMITS, FetchLimits
from pxapi.domain.site_discovery import is_admissible
from pxapi.domain.site_identity import canonical_origin, canonical_url_key, is_same_origin
from pxapi.ports.html_observation import HtmlUnreadable
from pxapi.ports.page_fetch import (
    FetchFailureKind,
    PageFetcher,
    PageFetchFailure,
    PageFetchOutcome,
)
from pxapi.ports.site_discovery import (
    BootstrapFailure,
    DiscoveryObservation,
    DiscoveryReport,
    SourceAttempt,
    SourceId,
    SourceOutcome,
)

#: Builds a fetcher narrowed to a scope, or unscoped when given ``None``. Injected so a test can
#: reach a controlled server on loopback through a test-only policy, exactly as the fetcher's own
#: tests do, without the product gaining a switch that could widen its policy in production.
FetcherFactory = Callable[[Callable[[str], bool] | None], PageFetcher]

#: Media types whose body this adapter reads links out of.
_HTML_MEDIA_TYPES = frozenset({"text/html", "application/xhtml+xml"})

#: Statuses that mean a source is not served where it would be. Anything else outside 2xx is
#: the server failing to answer, which is a component outside our runtime.
_ABSENT_STATUSES = frozenset({404, 410})

#: A document type or entity declaration anywhere in a sitemap. Neither is needed by the
#: sitemaps.org protocol, and entity expansion is exactly the attack surface a parser of
#: attacker-served XML must not open — so a sitemap carrying one is not parsed at all.
_DECLARATION = re.compile(rb"<!\s*(?:doctype|entity)", re.IGNORECASE)

#: The two root elements a sitemap document may have.
_URLSET = "urlset"
_SITEMAP_INDEX = "sitemapindex"

_GZIP_MAGIC = b"\x1f\x8b"

#: A body that begins like an HTML document. A robots file served as an HTML page — a soft 404
#: that answers 200 — is not a robots file, and reading ``Sitemap:`` lines out of markup would
#: invent declarations nobody made.
_HTML_START = re.compile(rb"^\s*(?:<!doctype\s+html|<html)", re.IGNORECASE)

#: When several sitemap documents end in different failures and none was read, the one the
#: aggregate reports. Our own refusal first, then the provider, then our runtime, then what the
#: document itself was — so the state reported is the one closest to *why nothing was read*.
_FAILURE_PRECEDENCE = (
    SourceOutcome.TARGET_POLICY_REFUSED,
    SourceOutcome.PROVIDER_FAILURE,
    SourceOutcome.RUNTIME_ERROR,
    SourceOutcome.MALFORMED,
    SourceOutcome.ABSENT,
)


def _media_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    return content_type.split(";")[0].strip().lower() or None


def _fetch_failure_outcome(kind: FetchFailureKind) -> SourceOutcome:
    """A fetch that produced no response, as a source outcome.

    ``BLOCKED_TARGET`` is our own policy or our own origin scope refusing, before any socket;
    ``TIMEOUT`` is a time budget; everything else — a name that did not resolve, a connection
    that did not hold, a peer that did not speak HTTP — is a component outside our runtime.
    """
    if kind is FetchFailureKind.BLOCKED_TARGET:
        return SourceOutcome.TARGET_POLICY_REFUSED
    if kind is FetchFailureKind.TIMEOUT:
        return SourceOutcome.TIMEOUT
    return SourceOutcome.PROVIDER_FAILURE


def _status_outcome(status: int) -> SourceOutcome | None:
    """``None`` for a response a source may be read from; otherwise why it may not."""
    if 200 <= status < 300:
        return None
    return SourceOutcome.ABSENT if status in _ABSENT_STATUSES else SourceOutcome.PROVIDER_FAILURE


def _guarded[T](step: Callable[[], T], failed: T) -> T:
    """``step()``, or ``failed`` when it raised.

    Each source is read under this guard so that a defect in one — a parser path nobody
    anticipated, a provider breaking its own contract — ends that source as our
    ``RUNTIME_ERROR`` and lets the others run. What it discards is only what the failed source
    had collected, which is exactly right: a source reported as failed admits nothing.
    """
    try:
        return step()
    except Exception:  # any defect in one source is one category to us
        return failed


class _Budget:
    """The request count and the deadline one discovery run shares across every source."""

    def __init__(self, limits: DiscoveryLimits, clock: Callable[[], float]) -> None:
        self.limits = limits
        self.clock = clock
        self.deadline = clock() + limits.total_deadline_seconds
        self.requests = 0

    def admit(self) -> SourceOutcome | None:
        """Take one request, or say which of our bounds refuses it."""
        if self.clock() >= self.deadline:
            return SourceOutcome.TIMEOUT
        if self.requests >= self.limits.max_requests:
            return SourceOutcome.BUDGET_EXHAUSTED
        self.requests += 1
        return None


@dataclass
class _SitemapRead:
    """What one sitemap document yielded, before it is folded into the aggregate."""

    outcome: SourceOutcome
    entries: list[str] = field(default_factory=list)
    children: list[str] = field(default_factory=list)


def _local(tag: str) -> str:
    """An element's local name: sitemaps are namespaced, and the namespace is not the point."""
    return tag.rpartition("}")[2]


def _xml_of(response: PageFetchOutcome, bound: int) -> tuple[bytes | None, bool]:
    """``(xml, cut)``: the sitemap bytes, gzip-inflated if need be, and whether a bound cut them.

    A ``.xml.gz`` sitemap is served as a gzip *file* rather than with a gzip content encoding, so
    the fetcher hands it over compressed. Inflation is bounded exactly like the read: a small
    compressed body may inflate to an arbitrarily large one. ``None`` is a body that claimed to be
    gzip and was not.
    """
    if not response.body.startswith(_GZIP_MAGIC):
        return response.body, response.truncated
    try:
        inflated = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(response.body, bound + 1)
    except zlib.error:
        return None, response.truncated
    if len(inflated) > bound:
        return inflated[:bound], True
    return inflated, response.truncated


def _parse_sitemap(xml: bytes) -> tuple[str | None, list[str], bool]:
    """``(root, locs, failed)`` for one sitemap document.

    Events are drawn one at a time because ``XMLPullParser`` queues a feed-time parse error
    *among* its events and re-raises it when iteration reaches it: every entry before the error
    is still returned, which is what lets a document our byte bound cut short contribute what
    was read. Whether a failed document is a cut one or a malformed one is the caller's call.
    """
    parser = XMLPullParser(events=("start", "end"))
    # Two different ways to fail, and both count. An error met while *feeding* is queued among
    # the events and re-raised when iteration reaches it; an error met at ``close()`` — a
    # document that simply stops, unclosed — is raised there and queued nowhere. Treating the
    # second as queued would read an unclosed sitemap as a complete, empty one.
    failed = False
    try:
        parser.feed(xml)
        parser.close()
    except ParseError:
        failed = True

    root: str | None = None
    stack: list[str] = []
    locs: list[str] = []
    events = parser.read_events()
    while True:
        try:
            event, element = next(events)
        except StopIteration:
            break
        except ParseError:
            failed = True
            break
        name = _local(element.tag)
        if event == "start":
            root = root or name
            stack.append(name)
            continue
        if name == "loc" and len(stack) >= 2 and stack[-2] in ("url", "sitemap"):
            text = (element.text or "").strip()
            if text:
                locs.append(text)
        if stack:
            stack.pop()
    return root, locs, failed


class HttpSiteDiscovery:
    """The static-HTTP ``SiteDiscoveryPort``: one origin, bounded sources, neutral outcomes."""

    def __init__(
        self,
        policy: PublicTargetPolicy | None = None,
        fetch_limits: FetchLimits = DEFAULT_FETCH_LIMITS,
        limits: DiscoveryLimits = DEFAULT_DISCOVERY_LIMITS,
        clock: Callable[[], float] = time.monotonic,
        fetcher_factory: FetcherFactory | None = None,
    ) -> None:
        self.limits = limits
        self.fetch_limits = fetch_limits
        self.clock = clock
        shared_policy = policy or PublicTargetPolicy()
        self.fetcher_factory: FetcherFactory = fetcher_factory or (
            lambda scope: SafePageFetcher(
                policy=shared_policy, limits=fetch_limits, clock=clock, scope=scope
            )
        )

    # --- the port ----------------------------------------------------------------------

    def discover(self, target_url: str) -> DiscoveryReport:
        budget = _Budget(self.limits, self.clock)

        submitted_origin = canonical_origin(target_url)
        if submitted_origin is None:
            # Refused by our own identity rules — a credential in the authority above all —
            # before any lookup or connection. It is our refusal, never a fact about the site.
            return DiscoveryReport(None, bootstrap_failure=BootstrapFailure.TARGET_REFUSED)

        if budget.admit() is not None:  # pragma: no cover - the first request always fits
            return DiscoveryReport(None, bootstrap_failure=BootstrapFailure.TIMEOUT)

        # The bootstrap is deliberately unscoped: it is what *establishes* the origin, so a
        # redirect from http://example.com to https://www.example.com must be followable. Each
        # hop is still re-validated and re-resolved by the policy.
        try:
            seed = self.fetcher_factory(None).fetch(submitted_origin)
        except Exception:
            # The port reports outcomes, never exceptions: a defect our runtime did not
            # anticipate is our runtime's failure, and it establishes no origin.
            return DiscoveryReport(None, bootstrap_failure=BootstrapFailure.RUNTIME_ERROR)
        if isinstance(seed, PageFetchFailure):
            return DiscoveryReport(None, bootstrap_failure=self._bootstrap_failure(seed.kind))

        origin = canonical_origin(seed.final_url)
        if origin is None:
            return DiscoveryReport(None, bootstrap_failure=BootstrapFailure.TARGET_REFUSED)

        def in_origin(url: str) -> bool:
            key = canonical_url_key(url)
            return key is not None and is_same_origin(key, origin)

        scoped = self.fetcher_factory(in_origin)
        observations = [DiscoveryObservation(origin, SourceId.CANONICAL_SEED.value)]
        attempts = [SourceAttempt(SourceId.CANONICAL_SEED.value, SourceOutcome.USED)]

        link_outcome, links = _guarded(
            lambda: self._links(seed, in_origin), (SourceOutcome.RUNTIME_ERROR, [])
        )
        observations += links
        attempts.append(SourceAttempt(SourceId.SAME_ORIGIN_PAGE_LINKS.value, link_outcome))

        robots_outcome, declared = _guarded(
            lambda: self._robots(scoped, origin, budget), (SourceOutcome.RUNTIME_ERROR, [])
        )
        attempts.append(SourceAttempt(SourceId.ROBOTS_DECLARATION.value, robots_outcome))

        sitemap_outcome, entries, off_origin = _guarded(
            lambda: self._sitemaps(scoped, origin, declared, in_origin, budget),
            (SourceOutcome.RUNTIME_ERROR, [], False),
        )
        observations += entries
        attempts.append(SourceAttempt(SourceId.SITEMAP.value, sitemap_outcome))
        if off_origin:
            attempts.append(
                SourceAttempt(
                    SourceId.OFF_ORIGIN_SITEMAP.value, SourceOutcome.TARGET_POLICY_REFUSED
                )
            )

        return DiscoveryReport(
            target_origin=origin, observations=tuple(observations), attempts=tuple(attempts)
        )

    @staticmethod
    def _bootstrap_failure(kind: FetchFailureKind) -> BootstrapFailure:
        if kind is FetchFailureKind.BLOCKED_TARGET:
            return BootstrapFailure.TARGET_REFUSED
        if kind is FetchFailureKind.TIMEOUT:
            return BootstrapFailure.TIMEOUT
        return BootstrapFailure.UNREACHABLE

    # --- links from the seed document ----------------------------------------------------

    def _links(
        self, seed: PageFetchOutcome, in_origin: Callable[[str], bool]
    ) -> tuple[SourceOutcome, list[DiscoveryObservation]]:
        """Same-origin links from the seed document, in document order, bounded.

        The seed response is reused rather than fetched again: one page is read for links,
        and it is the page the bootstrap already retrieved. Only same-origin targets become
        observations — the source is *same-origin* page links by definition — and only those
        the Domain would admit, so this outcome and the admitted count cannot disagree.
        """
        refused = _status_outcome(seed.status_code)
        if refused is not None:
            return refused, []
        if _media_type(seed.content_type) not in _HTML_MEDIA_TYPES:
            return SourceOutcome.MALFORMED, []
        if seed.undecodable:
            return SourceOutcome.RUNTIME_ERROR, []
        try:
            links = read_links(
                seed.body, seed.final_url, seed.declared_charset, self.limits.max_label_length
            )
        except HtmlUnreadable:
            return SourceOutcome.RUNTIME_ERROR, []

        observed: list[DiscoveryObservation] = []
        keys: set[str] = set()
        exhausted = False
        for link in links:
            observation = DiscoveryObservation(
                link.href, SourceId.SAME_ORIGIN_PAGE_LINKS.value, link.label
            )
            if not in_origin(link.href) or not is_admissible(observation):
                continue
            key = canonical_url_key(link.href)
            if key not in keys and len(keys) >= self.limits.max_page_links:
                exhausted = True
                break
            keys.add(key or "")
            observed.append(observation)

        if exhausted or seed.truncated:
            return SourceOutcome.BUDGET_EXHAUSTED, observed
        return (SourceOutcome.USED if observed else SourceOutcome.EMPTY), observed

    # --- robots.txt, for Sitemap: and nothing else ----------------------------------------

    def _robots(
        self, fetcher: PageFetcher, origin: str, budget: _Budget
    ) -> tuple[SourceOutcome, list[str]]:
        """The sitemap declarations ``/robots.txt`` makes, and what became of reading it.

        A robots file contributes no page candidates: its declarations are references to
        sitemaps, not pages. Only the ``Sitemap`` field is read; every other line is ignored,
        which is precisely why this slice claims no robots compliance of any kind.
        """
        refused = budget.admit()
        if refused is not None:
            return refused, []
        response = fetcher.fetch(urljoin(origin, "/robots.txt"))
        if isinstance(response, PageFetchFailure):
            return _fetch_failure_outcome(response.kind), []
        status = _status_outcome(response.status_code)
        if status is not None:
            return status, []
        if response.undecodable:
            return SourceOutcome.RUNTIME_ERROR, []
        if (
            _media_type(response.content_type) in _HTML_MEDIA_TYPES
            or _HTML_START.match(response.body)
            or b"\x00" in response.body
        ):
            return SourceOutcome.MALFORMED, []

        declared: list[str] = []
        # The shared decoder, not ``bytes.decode``: a declared charset nobody has heard of is
        # the server's typo, and it must fall back to UTF-8 rather than raise ``LookupError``.
        text = decode_body(response.body, response.declared_charset)
        for line in text.splitlines():
            field_name, separator, value = line.split("#", 1)[0].partition(":")
            if separator and field_name.strip().lower() == "sitemap" and value.strip():
                declared.append(urljoin(response.final_url, value.strip()))

        if response.truncated:
            return SourceOutcome.BUDGET_EXHAUSTED, declared
        return (SourceOutcome.USED if declared else SourceOutcome.NO_SITEMAP_DECLARATION), declared

    # --- sitemaps ----------------------------------------------------------------------

    def _sitemaps(
        self,
        fetcher: PageFetcher,
        origin: str,
        declared: list[str],
        in_origin: Callable[[str], bool],
        budget: _Budget,
    ) -> tuple[SourceOutcome, list[DiscoveryObservation], bool]:
        """Read the same-origin sitemaps, bounded; report off-origin references, never fetch them.

        When robots declares no same-origin sitemap, the conventional ``/sitemap.xml`` is
        tried instead. Index documents name further sitemaps, which join the same bounded
        queue. Returns ``(aggregate outcome, entry observations, any off-origin reference)``.
        """
        queue: list[str] = []
        seen: set[str] = set()
        off_origin = False
        budget_cut = False

        def plan(url: str) -> None:
            nonlocal off_origin, budget_cut
            key = canonical_url_key(url)
            if key is None or key in seen:
                return  # refused before persistence, or already planned
            if not in_origin(key):
                off_origin = True
                return
            if len(queue) >= self.limits.max_sitemap_documents:
                budget_cut = True
                return
            seen.add(key)
            queue.append(key)

        for url in declared:
            plan(url)
        if not queue:
            plan(urljoin(origin, "/sitemap.xml"))

        reads: list[_SitemapRead] = []
        entries: list[DiscoveryObservation] = []
        index = 0
        while index < len(queue):
            if len(entries) >= self.limits.max_sitemap_entries:
                # The entry budget is spent: a further document could only be read to be
                # discarded, so it is not fetched at all, and the bound is what is reported.
                budget_cut = True
                break
            refused = budget.admit()
            if refused is not None:
                reads.append(_SitemapRead(refused))
                break
            read = self._read_sitemap(fetcher, queue[index])
            index += 1
            reads.append(read)
            for child in read.children:
                plan(child)
            for entry in read.entries:
                if len(entries) >= self.limits.max_sitemap_entries:
                    budget_cut = True
                    break
                observation = DiscoveryObservation(entry, SourceId.SITEMAP.value)
                if is_admissible(observation):
                    entries.append(observation)

        return self._aggregate(reads, budget_cut), entries, off_origin

    def _read_sitemap(self, fetcher: PageFetcher, url: str) -> _SitemapRead:
        response = fetcher.fetch(url)
        if isinstance(response, PageFetchFailure):
            return _SitemapRead(_fetch_failure_outcome(response.kind))
        status = _status_outcome(response.status_code)
        if status is not None:
            return _SitemapRead(status)
        if response.undecodable:
            return _SitemapRead(SourceOutcome.RUNTIME_ERROR)

        xml, cut = _xml_of(response, self.fetch_limits.max_response_bytes)
        if xml is None:
            return _SitemapRead(SourceOutcome.BUDGET_EXHAUSTED if cut else SourceOutcome.MALFORMED)
        if _DECLARATION.search(xml):
            return _SitemapRead(SourceOutcome.MALFORMED)

        root, locs, failed = _parse_sitemap(xml)
        if root is not None and root not in (_URLSET, _SITEMAP_INDEX):
            return _SitemapRead(SourceOutcome.MALFORMED)
        if failed and not cut:
            # Served, but not parseable as a sitemap. Whatever came before the error is
            # discarded: a source reported MALFORMED is structurally pinned to zero admitted.
            return _SitemapRead(SourceOutcome.MALFORMED)

        outcome = (
            SourceOutcome.BUDGET_EXHAUSTED
            if cut
            else (SourceOutcome.USED if locs else SourceOutcome.EMPTY)
        )
        if root == _SITEMAP_INDEX:
            return _SitemapRead(outcome, children=locs)
        return _SitemapRead(outcome, entries=locs)

    @staticmethod
    def _aggregate(reads: list[_SitemapRead], budget_cut: bool) -> SourceOutcome:
        """One outcome for the whole sitemap source, which the contract reports exactly once.

        A bound of ours that stopped the reading wins, because it is what makes the admitted
        count a partial one; then the clock; then any document that was read. Only when nothing
        was read at all does a failure speak for the source. The order is forced by the contract
        rather than chosen: an outcome under which admission is impossible must report zero, so
        it can never stand for a source that did contribute candidates.
        """
        outcomes = {read.outcome for read in reads}
        if budget_cut or SourceOutcome.BUDGET_EXHAUSTED in outcomes:
            return SourceOutcome.BUDGET_EXHAUSTED
        if SourceOutcome.TIMEOUT in outcomes:
            return SourceOutcome.TIMEOUT
        if SourceOutcome.USED in outcomes:
            return SourceOutcome.USED
        if SourceOutcome.EMPTY in outcomes:
            return SourceOutcome.EMPTY
        for failure in _FAILURE_PRECEDENCE:
            if failure in outcomes:
                return failure
        return SourceOutcome.ABSENT  # pragma: no cover - at least one document is always read
