"""Hostile input cannot make discovery exceed its declared bounds: time, memory or work.

Every case is a reproduction from the adversarial robustness review, reduced to the smallest
input that shows the defect and run under small limits so the suite stays fast. A bound that only
held for polite servers would not be a bound, and the smoke's evidence ceiling depends on these.
"""

from __future__ import annotations

import threading
import time
import tracemalloc
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ClassVar

import pytest

from pxapi.adapters.web import site_discovery as adapter
from pxapi.adapters.web.html_links import read_links
from pxapi.adapters.web.page_fetcher import SafePageFetcher
from pxapi.adapters.web.site_discovery import HttpSiteDiscovery
from pxapi.config.discovery_limits import DiscoveryLimits
from pxapi.config.fetch_limits import FetchLimits
from pxapi.domain import site_identity
from pxapi.domain.site_discovery import admitted_observations, assemble_candidates
from pxapi.domain.site_identity import UrlRefusal, canonical_url_key, refuse
from pxapi.ports.page_fetch import FetchFailureKind, PageFetchFailure
from tests.adapters.http_test_server import Route, loopback_policy
from tests.adapters.test_site_discovery_adapter import (
    NS,
    XML,
    discover,
    forms,
    home,
    outcomes,
    robots,
    urlset,
)

UTF8_BOM = bytes([0xEF, 0xBB, 0xBF])


class _Trickler(BaseHTTPRequestHandler):
    """Serves fast paths normally and trickles one byte per interval on the others."""

    protocol_version = "HTTP/1.1"
    fast: ClassVar[dict[str, bytes]] = {}
    slow: ClassVar[dict[str, bytes]] = {}
    interval: ClassVar[float] = 0.25

    def do_GET(self) -> None:
        body = self.fast.get(self.path, self.slow.get(self.path))
        if body is None:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html" if self.path == "/" else "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.path in self.fast:
            self.wfile.write(body)
            return
        for byte in body:
            try:
                self.wfile.write(bytes([byte]))
                self.wfile.flush()
            except OSError:
                return
            time.sleep(self.interval)

    def log_message(self, *args: Any) -> None:
        """Silence."""


@contextmanager
def trickling(fast: dict[str, bytes], slow: dict[str, bytes]) -> Iterator[str]:
    handler = type("Bound", (_Trickler,), {"fast": fast, "slow": slow})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.block_on_close = False
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


# --- time ---------------------------------------------------------------------------------


def test_a_trickling_body_cannot_outlive_the_fetch_deadline() -> None:
    """A per-receive timeout resets on every byte, so it bounds nothing against a trickle."""
    with trickling({}, {"/": b"x" * 40}) as base:
        fetcher = SafePageFetcher(
            policy=loopback_policy(),
            limits=FetchLimits(read_timeout_seconds=1.0, total_deadline_seconds=1.5),
        )
        started = time.monotonic()
        result = fetcher.fetch(base + "/")
        elapsed = time.monotonic() - started
    assert result == PageFetchFailure(FetchFailureKind.TIMEOUT)
    assert elapsed < 3.0, elapsed


def test_one_slow_source_cannot_hold_a_discovery_past_its_own_deadline() -> None:
    with trickling({"/": b"<html></html>"}, {"/robots.txt": b"#" * 100}) as base:
        discovery = HttpSiteDiscovery(
            policy=loopback_policy(),
            fetch_limits=FetchLimits(read_timeout_seconds=1.0, total_deadline_seconds=20.0),
            limits=DiscoveryLimits(total_deadline_seconds=2.0),
        )
        started = time.monotonic()
        report = discovery.discover(base + "/")
        elapsed = time.monotonic() - started
    assert outcomes(report)["ROBOTS_DECLARATION"] == "TIMEOUT"
    assert elapsed < 4.5, elapsed


def test_canonicalising_a_megabyte_value_is_refused_at_once() -> None:
    """No written form longer than the contract's bound can ever be persisted, so none is worth
    the work of canonicalising: it is refused before any of it."""
    value = "https://example.com/" + "a/" * 500_000
    started = time.monotonic()
    assert refuse(value) is UrlRefusal.TOO_LONG
    assert canonical_url_key(value) is None
    assert time.monotonic() - started < 0.5


# --- the sitemap parser -------------------------------------------------------------------


def test_a_utf16_sitemap_declaring_entities_is_refused_like_any_other() -> None:
    """A byte-level guard cannot see a declaration written in UTF-16; the parser can."""

    def routes(b: str) -> dict[str, Route]:
        xml = (
            '<?xml version="1.0" encoding="UTF-16"?>'
            '<!DOCTYPE u [<!ENTITY e "smuggled">]>'
            f"<urlset {NS}><url><loc>{b}/&e;</loc></url></urlset>"
        )
        return {"/": home(), "/sitemap.xml": Route(body=xml.encode("utf-16"), headers=XML)}

    report, _ = discover(routes)
    assert outcomes(report)["SITEMAP"] == "MALFORMED"
    assert forms(report, "SITEMAP") == []


def test_a_sitemap_in_an_encoding_we_cannot_read_fails_alone() -> None:
    """One document's defect must not discard what its siblings already contributed."""
    report, base = discover(
        lambda b: {
            "/": home(),
            "/robots.txt": robots(f"Sitemap: {b}/gut.xml", f"Sitemap: {b}/fremd.xml"),
            "/gut.xml": urlset(b + "/gefunden"),
            "/fremd.xml": Route(
                body=(
                    b'<?xml version="1.0" encoding="x-nope"?>'
                    b"<urlset><url><loc>x</loc></url></urlset>"
                ),
                headers=XML,
            ),
        }
    )
    assert outcomes(report)["SITEMAP"] == "USED"
    assert forms(report, "SITEMAP") == [base + "/gefunden"]


def test_a_robots_file_that_begins_with_a_byte_order_mark_is_read_from_its_first_line() -> None:
    report, base = discover(
        lambda b: {
            "/": home(),
            "/robots.txt": Route(body=UTF8_BOM + f"Sitemap: {b}/s.xml\n".encode(), headers={}),
            "/s.xml": urlset(b + "/x"),
        }
    )
    assert outcomes(report)["ROBOTS_DECLARATION"] == "USED"
    assert forms(report, "SITEMAP") == [base + "/x"]


def test_a_deeply_nested_sitemap_is_refused_without_building_a_tree() -> None:
    deep = b"<urlset>" + b"<a>" * 60_000 + b"</a>" * 60_000 + b"</urlset>"
    tracemalloc.start()
    try:
        parsed = adapter._parse_sitemap(deep)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert parsed.refused and parsed.locs == []
    assert peak < 4 * 1024 * 1024, peak


# --- work ---------------------------------------------------------------------------------


@pytest.fixture
def canonicalisations(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Counts how often the one canonicalisation decision is taken."""
    calls = [0]
    real = site_identity._canonicalise

    def counting(value: str) -> Any:
        calls[0] += 1
        return real(value)

    monkeypatch.setattr(site_identity, "_canonicalise", counting)
    return calls


def test_a_repeated_anchor_is_canonicalised_once(canonicalisations: list[int]) -> None:
    anchors = [("/kontakt", "Kontakt")] * 5000
    discover(lambda b: {"/": home(*anchors)})
    assert canonicalisations[0] < 200, canonicalisations[0]


def test_the_links_examined_are_bounded_as_well_as_the_links_admitted() -> None:
    foreign = [(f"https://elsewhere.test/{i}", "x") for i in range(30)]
    report, _ = discover(
        lambda b: {"/": home(*foreign)}, limits=DiscoveryLimits(max_links_examined=10)
    )
    assert outcomes(report)["SAME_ORIGIN_PAGE_LINKS"] == "BUDGET_EXHAUSTED"


def test_a_robots_file_of_many_declarations_is_planned_only_up_to_the_queue(
    canonicalisations: list[int],
) -> None:
    lines = [f"Sitemap: /s{i}.xml" for i in range(5000)]
    report, _ = discover(
        lambda b: {"/": home(), "/robots.txt": robots(*lines)},
        limits=DiscoveryLimits(max_sitemap_documents=2),
    )
    assert outcomes(report)["SITEMAP"] == "BUDGET_EXHAUSTED"
    assert canonicalisations[0] < 200, canonicalisations[0]


@pytest.mark.parametrize("unit", [b"<a", b"<!--", b"<a href='"], ids=["lt_a", "comment", "attr"])
def test_the_link_reader_is_linear_on_markup_left_unterminated(unit: bytes) -> None:
    """Measured on CPython 3.13.3: 128 KB of '<a' took 20.8 s, because HTMLParser.close()
    reprocesses an unterminated construct character by character on that release. The reader
    never calls close(), so no interpreter release can make this quadratic again."""
    body = unit * (65536 // len(unit))
    started = time.monotonic()
    read_links(body, "https://example.com/", "utf-8", 120)
    assert time.monotonic() - started < 1.0


def test_one_sitemap_whose_read_raises_does_not_discard_its_siblings() -> None:
    """Each document is read under its own guard, so an unanticipated defect in one ends that
    document as our RUNTIME_ERROR and leaves the entries its siblings contributed in place."""

    class Selective:
        def __init__(self, inner: SafePageFetcher) -> None:
            self.inner = inner

        def fetch(self, url: str) -> Any:
            if url.endswith("/boom.xml"):
                raise RuntimeError("an unanticipated defect")
            return self.inner.fetch(url)

    def factory(scope: Any) -> Any:
        inner = SafePageFetcher(policy=loopback_policy(), scope=scope)
        return Selective(inner) if scope is not None else inner

    report, base = discover(
        lambda b: {
            "/": home(),
            "/robots.txt": robots(f"Sitemap: {b}/gut.xml", f"Sitemap: {b}/boom.xml"),
            "/gut.xml": urlset(b + "/gefunden"),
        },
        fetcher_factory=factory,
    )
    assert outcomes(report)["SITEMAP"] == "USED"
    assert forms(report, "SITEMAP") == [base + "/gefunden"]


# --- C-PXAPI-016: what the declared bounds promise, measured --------------------------------
#
# The finding names two paths. These tests measure each against the bound's own wording in
# src/pxapi/config/discovery_limits.py, because a bound can only be violated relative to what it
# says. They are locks on behaviour that is already correct, not a repair.


@pytest.fixture
def documents_read(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every URL a sitemap read actually fetched — the unit ``max_sitemap_documents`` bounds."""
    seen: list[str] = []
    real = HttpSiteDiscovery._read_sitemap

    def recording(self: Any, fetcher: Any, url: str) -> Any:
        seen.append(url)
        return real(self, fetcher, url)

    monkeypatch.setattr(HttpSiteDiscovery, "_read_sitemap", recording)
    return seen


def test_off_origin_declarations_read_no_document_at_all(
    documents_read: list[str], canonicalisations: list[int]
) -> None:
    """C-PXAPI-016 A. ``max_sitemap_documents`` bounds "sitemap documents one discovery may
    read". An off-origin declaration is refused before the queue and is therefore never read,
    so the declared bound is honoured by a wide margin: zero declared documents are read, and
    the one conventional ``/sitemap.xml`` fallback is all that is fetched."""
    lines = [f"Sitemap: https://elsewhere{i}.test/s.xml" for i in range(2000)]
    report, base = discover(
        lambda b: {"/": home(), "/robots.txt": robots(*lines)},
        limits=DiscoveryLimits(max_sitemap_documents=5),
    )
    assert documents_read == [base + "/sitemap.xml"]
    assert len(documents_read) <= 5
    assert outcomes(report)["REFUSED_SITEMAP"] == "TARGET_POLICY_REFUSED"
    assert forms(report, "SITEMAP") == []
    # The work of refusing them is linear in the declarations, which the outer FetchLimits
    # response-byte cap bounds: it is not free, and it is not unbounded either.
    assert canonicalisations[0] <= 6 * len(lines), canonicalisations[0]


def test_the_refusing_path_stays_inside_the_declared_discovery_deadline() -> None:
    """The same path filled to the outer byte cap: ``FetchLimits.max_response_bytes`` is what
    bounds how many declarations can exist at all, and the run finishes well inside the
    ``DiscoveryLimits`` deadline with no candidate admitted from the source."""
    limits = DiscoveryLimits(total_deadline_seconds=60.0)
    fetch_limits = FetchLimits(max_response_bytes=256 * 1024)
    line = "Sitemap:http://a.aa/"  # 20 chars + newline: the shortest usable off-origin form
    lines = [line] * (fetch_limits.max_response_bytes // (len(line) + 1))
    started = time.monotonic()
    report, _ = discover(
        lambda b: {"/": home(), "/robots.txt": robots(*lines)},
        limits=limits,
        fetch_limits=fetch_limits,
    )
    elapsed = time.monotonic() - started
    assert elapsed < limits.total_deadline_seconds, elapsed
    assert forms(report, "SITEMAP") == []


def test_many_labels_for_one_href_cost_one_written_target_and_one_candidate() -> None:
    """C-PXAPI-016 B. ``max_page_links`` bounds "distinct written same-origin link targets
    admitted", and that is exactly what it bounds here: 300 anchors to one target are one
    target and — after the Domain folds observations onto identities — one candidate. The
    transient observations that carry the distinct labels are a classification signal, never a
    page, and no member of the inventory counts them."""
    limits = DiscoveryLimits(max_page_links=5)
    anchors = [("/eine-seite", f"label-{i}") for i in range(300)]
    report, base = discover(lambda b: {"/": home(*anchors)}, limits=limits)

    written = forms(report, "SAME_ORIGIN_PAGE_LINKS")
    # The multiplication the finding names is real and is measured here rather than assumed:
    # one target under 300 labels yields 300 observations, far past ``max_page_links``. Without
    # this assertion the two below would hold vacuously on a run that emitted one observation.
    assert len(written) == len(anchors) > limits.max_page_links

    # What the bound actually promises, and what it actually delivers: distinct written targets.
    assert set(written) == {base + "/eine-seite"}
    assert len(set(written)) <= limits.max_page_links

    # And the persisted population, which is what an inventory carries: one page, not 300.
    candidates = assemble_candidates(
        admitted_observations(report.observations), report.target_origin or ""
    )
    from_links = [c for c in candidates if "SAME_ORIGIN_PAGE_LINKS" in c.provenance]
    assert len(from_links) == 1 <= limits.max_page_links
    assert outcomes(report)["SAME_ORIGIN_PAGE_LINKS"] == "USED"


def test_the_distinct_target_bound_genuinely_bites() -> None:
    """The control the test above needs: the same bound, under distinct targets, does stop the
    read and says so — so the assertion above is a bound holding, not a bound never reached."""
    limits = DiscoveryLimits(max_page_links=5)
    report, _ = discover(
        lambda b: {"/": home(*[(f"/p{i}", f"p{i}") for i in range(100)])}, limits=limits
    )
    written = forms(report, "SAME_ORIGIN_PAGE_LINKS")
    assert len(set(written)) == 5
    assert outcomes(report)["SAME_ORIGIN_PAGE_LINKS"] == "BUDGET_EXHAUSTED"
