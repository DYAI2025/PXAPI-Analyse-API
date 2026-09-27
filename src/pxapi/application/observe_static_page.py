"""Observing one *selected* page over static HTTP, with no homepage semantics anywhere in it.

This is the generic half of what the homepage use case does, and deliberately only that half.
It is handed the outcome of one page fetch and returns the page-scoped measurements and evidence
that outcome supports — no run lifecycle, no stage records, no envelope, no findings. What to do
with a page that failed, and which pages to fetch at all, belong to the multi-page runtime; this
module answers one question about one page and nothing else.

It is a **separate path** rather than an extraction out of ``AnalyzeHomepage``, which stays
byte-identical: D-20-E judged the shipped homepage use case too valuable to put into a
pre-revenue refactor, and preferred a small intentional duplication. The duplication is bounded
to the observation logic; every decision underneath it — the metric vocabulary, the text
representability rule, the generic-noindex channels, the fetch port's own outcome shapes — is
reused from the Domain and the Ports rather than restated.

Four things differ from the homepage profile, and each is a decision rather than an accident.

**No combined noindex record.** The homepage profile emits a third, combined
``HOMEPAGE_GENERIC_NOINDEX_PRESENT`` measurement because a homepage finding rule has to read one
value. No page rule exists, so the page profile emits the two channel records and invents no new
metric id: thirteen measurements where the homepage emits fourteen.

**A canonical link is resolved strictly.** Site-controlled HTML can declare a canonical that the
URL parser refuses outright, or that resolves to a value no measurement carrier can hold. Both
become an assessment that established nothing, while the *presence* fact stays KNOWN — a page
that declares a canonical did declare one, whatever its value turns out to be. That contains the
class of input recorded as ``C-PXAPI-018`` for pages, and makes no claim about the homepage path.

**A URL value is bounded by the URL contract, not by the text bound.** The homepage profile
gates every observed value on the 500-character ``single_line_text`` bound, URL values included.
A ``url_value`` is carried by ``common#/$defs/url``, whose bound is 2048, so a 600-character
canonical is representable and recording UNKNOWN for it would be a *false* UNKNOWN — a statement
that we established nothing about a value we established perfectly well. The text bound still
governs every TEXT value, because that is the bound those members actually have.

**A page whose own URLs are unrepresentable is withheld whole.** Some canonical page identities
cannot be carried by ``common#/$defs/url`` at all (``C-PXAPI-020``). Publishing the facts whose
source URL happens to fit and dropping the rest would leave a half-measured page; publishing
none of them silently would leave a gap a reader could attribute to the site. So the observation
comes back empty with the reason stated, and the acquisition record carries that reason.

**An error document is not page content (PXAPI-20.B, D-20-F).** A non-2xx response is still a
received response and its transport facts are measured, but its body is never parsed: the
document facts and the meta-robots channel are ``NOT_ASSESSED`` with ``UNSUPPORTED``, so the
title of a 404 template can never be read as the selected page's title.

The layer holds no transport and no parser: it is handed a reader and an id factory, which is
what lets one frozen input produce byte-identical documents on every run.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final
from urllib.parse import urljoin

from pxapi.domain.indexability import (
    GenericNoindex,
    meta_robots_generic_noindex,
    x_robots_tag_generic_noindex,
)
from pxapi.domain.observations import Metric, normalise_single_line, representable_text
from pxapi.domain.page_acquisition import is_contract_url, withheld_reason_for
from pxapi.ports.html_observation import HtmlObservations, HtmlReader, HtmlUnreadable
from pxapi.ports.page_fetch import (
    FetchFailureKind,
    PageFetchFailure,
    PageFetchOutcome,
    PageFetchResult,
)

#: Who made the observation, and by which method. A page-generic token: nothing in the emitted
#: documents may name the homepage, on the success path or on the failure path.
STATIC_PAGE_COLLECTOR: Final = "STATIC_PAGE_BASELINE_COLLECTOR"
STATIC_PAGE_COLLECTOR_VERSION: Final = "1.0.0"

#: The context every observation of a selected page is made in.
SCENARIO_SELECTED_PAGE_STATIC_FETCH: Final = "SELECTED_PAGE_STATIC_FETCH"

#: Why *we* did not measure, per fetch outcome. Every value names our side of the attempt, and
#: the mapping is total over the port's vocabulary — a kind with no entry would raise here rather
#: than quietly produce a record with no reason.
NOT_ASSESSED_FOR: Final[dict[FetchFailureKind, str]] = {
    FetchFailureKind.BLOCKED_TARGET: "PERMISSION_DENIED",
    FetchFailureKind.DNS_FAILURE: "PROVIDER_FAILURE",
    FetchFailureKind.CONNECTION_FAILURE: "PROVIDER_FAILURE",
    FetchFailureKind.TIMEOUT: "TIMEOUT",
    FetchFailureKind.TOO_MANY_REDIRECTS: "PROVIDER_FAILURE",
    FetchFailureKind.INVALID_REDIRECT: "PROVIDER_FAILURE",
    FetchFailureKind.PROTOCOL_ERROR: "PROVIDER_FAILURE",
}

#: The statuses whose body this profile reads as the page's own content. Any other received
#: response is still measured — its status, final URL and headers are transport facts — but its
#: body is an error or interim document, and what it declares is not the page's content (D-20-F).
SUCCESS_STATUSES: Final = range(200, 300)

#: Why the document facts of a non-2xx response were not assessed: this profile does not read an
#: error document as page content. A statement about the profile, never about the page.
NON_SUCCESS_NOT_ASSESSED: Final = "UNSUPPORTED"

#: The media types this profile reads as a document. Anything else is a subject the document
#: metrics do not apply to, which is a fact about the measurement and not about the page.
HTML_MEDIA_TYPES: Final[frozenset[str]] = frozenset({"text/html", "application/xhtml+xml"})

#: The document elements, in the order their records are emitted.
HTML_METRICS: Final[tuple[Metric, ...]] = (
    Metric.PAGE_TITLE_PRESENT,
    Metric.PAGE_TITLE,
    Metric.META_DESCRIPTION_PRESENT,
    Metric.META_DESCRIPTION,
    Metric.CANONICAL_PRESENT,
    Metric.CANONICAL_URL,
)

#: The two generic-noindex channels, each recorded on its own. There is deliberately no third,
#: combined record: that one exists for a homepage finding rule, and no page rule exists.
INDEXABILITY_METRICS: Final[tuple[Metric, ...]] = (
    Metric.META_ROBOTS_GENERIC_NOINDEX_PRESENT,
    Metric.X_ROBOTS_TAG_GENERIC_NOINDEX_PRESENT,
)

#: Every metric one selected page produces, in emission order. Thirteen, and a proper subset of
#: the homepage profile's fourteen: this slice invents no metric id.
PAGE_METRICS: Final[tuple[Metric, ...]] = (
    Metric.HTTP_STATUS,
    Metric.FINAL_URL,
    Metric.CONTENT_TYPE,
    Metric.TRANSPORT_IS_HTTPS,
    Metric.REDIRECT_COUNT,
    *HTML_METRICS,
    *INDEXABILITY_METRICS,
)

#: The two facts that are about the *path taken*, so they are observed against the identity that
#: was requested. Every other fact is about the response, and is observed against the URL it
#: came from.
PATH_OUTCOME_METRICS: Final[frozenset[Metric]] = frozenset(
    {Metric.FINAL_URL, Metric.REDIRECT_COUNT}
)


class DocumentStatus(StrEnum):
    """What became of the attempt to read this page's document.

    It is not a run state and not a stage status: it says what the observation could do, so the
    multi-page runtime can record a stage outcome without re-deriving it from thirteen records.
    """

    #: The response was a document and the parser read it.
    READ = "READ"
    #: A response arrived but was not a document, so the document metrics do not apply.
    NOT_A_DOCUMENT = "NOT_A_DOCUMENT"
    #: A response arrived and *we* could not read it — an encoding we cannot decode, or our
    #: parser failing. A statement about our runtime, never about the page.
    UNREADABLE = "UNREADABLE"
    #: No response arrived at all.
    NO_RESPONSE = "NO_RESPONSE"
    #: Nothing was observed, because this page's own URLs are not representable in our contracts.
    WITHHELD = "WITHHELD"
    #: A response arrived with a non-2xx status, so its body was not read as page content.
    NON_SUCCESS_STATUS = "NON_SUCCESS_STATUS"


@dataclass(frozen=True)
class PageObservation:
    """Everything one page observation produced, and nothing derived from it.

    There is deliberately no findings member: a diagnostic finding is a statement about a website
    made by an authorised rule, and no rule of this repository is authorised to make one about a
    subpage. ``withheld_reason`` is set exactly when both document lists are empty.
    """

    measurements: tuple[dict[str, Any], ...]
    evidence: tuple[dict[str, Any], ...]
    document_status: DocumentStatus
    withheld_reason: str | None = None


def media_type_of(content_type: str | None) -> str | None:
    """The bare media type of a ``Content-Type`` header, lowercased."""
    if not content_type:
        return None
    return content_type.split(";")[0].strip().lower() or None


def _meta_robots_channel(observed: HtmlObservations, response: PageFetchOutcome) -> GenericNoindex:
    """What the document's generic robots declarations established, given how much we read.

    We stopped reading at our own byte bound, so a declaration further down would have been
    missed and "this document declares no generic noindex" is a claim the read cannot support. A
    directive we *did* see stands regardless: truncation can hide a declaration, never invent one.
    """
    observation = meta_robots_generic_noindex(observed.robots_meta_contents)
    if observation is GenericNoindex.ABSENT and response.truncated:
        return GenericNoindex.INDETERMINATE
    return observation


class StaticPageObserver:
    """Turns one page fetch outcome into page-scoped measurements and mirroring evidence."""

    def __init__(
        self,
        read_html: HtmlReader,
        new_id: Callable[[], str],
        max_text_length: int,
    ) -> None:
        self.read_html = read_html
        self.new_id = new_id
        # Read out of the contract by the caller, never restated here: a bound duplicated in a
        # collector is a bound that can silently disagree with the schema it claims to respect.
        self.max_text_length = max_text_length

    # --- the observation ---------------------------------------------------------------

    def observe(
        self, run_id: str, url_key: str, result: PageFetchResult, observed_at: str
    ) -> PageObservation:
        """Observe one selected page, given what its fetch produced.

        ``url_key`` is the selected page's canonical identity and ``observed_at`` the instant the
        attempt ended. Both are the caller's: this module reads no clock and issues no identity
        it was not handed a factory for, which is what makes one frozen input reproducible.
        """
        final_url = result.final_url if isinstance(result, PageFetchOutcome) else None
        withheld = withheld_reason_for(url_key, final_url)
        if withheld is not None:
            # Neither a document nor a partial one: publishing the facts whose source URL happens
            # to fit would leave a half-measured page, and publishing none of them silently would
            # leave a gap a reader could attribute to the site.
            return PageObservation((), (), DocumentStatus.WITHHELD, withheld)

        if isinstance(result, PageFetchFailure):
            measurements = tuple(
                self._not_assessed(
                    run_id, metric, url_key, observed_at, NOT_ASSESSED_FOR[result.kind]
                )
                for metric in PAGE_METRICS
            )
            return self._observation(measurements, DocumentStatus.NO_RESPONSE)

        measurements, status = self._measured(run_id, url_key, result, observed_at)
        return self._observation(tuple(measurements), status)

    def _observation(
        self, measurements: tuple[dict[str, Any], ...], status: DocumentStatus
    ) -> PageObservation:
        """Every measurement first, then its evidence — the id order a frozen input reproduces."""
        evidence = tuple(self._evidence_for(record) for record in measurements)
        return PageObservation(measurements, evidence, status)

    def _measured(
        self, run_id: str, url_key: str, response: PageFetchOutcome, observed_at: str
    ) -> tuple[list[dict[str, Any]], DocumentStatus]:
        measurements: list[dict[str, Any]] = []

        def source_for(metric: Metric) -> str:
            return url_key if metric in PATH_OUTCOME_METRICS else response.final_url

        def known(metric: Metric, mode: str, value_type: str, member: str, value: Any) -> None:
            measurements.append(
                self._record(
                    run_id,
                    metric,
                    source_for(metric),
                    observed_at,
                    {"collection_mode": mode, "result_state": "KNOWN"},
                    result={"value_type": value_type, member: value},
                )
            )

        def performed(metric: Metric, mode: str, result_state: str) -> None:
            measurements.append(
                self._record(
                    run_id,
                    metric,
                    source_for(metric),
                    observed_at,
                    {"collection_mode": mode, "result_state": result_state},
                )
            )

        # --- transport facts. Each is a measurement, never a verdict. -------------------
        known(Metric.HTTP_STATUS, "MEASURED", "INTEGER", "integer_value", response.status_code)
        known(Metric.FINAL_URL, "OBSERVED", "URL", "url_value", response.final_url)
        known(Metric.TRANSPORT_IS_HTTPS, "OBSERVED", "BOOLEAN", "boolean_value", response.is_https)
        known(
            Metric.REDIRECT_COUNT, "MEASURED", "INTEGER", "integer_value", response.redirect_count
        )

        content_type = representable_text(response.content_type or "", self.max_text_length)
        if content_type is None:
            performed(Metric.CONTENT_TYPE, "OBSERVED", "UNKNOWN")
        else:
            known(Metric.CONTENT_TYPE, "OBSERVED", "TEXT", "text_value", content_type)

        # --- document facts --------------------------------------------------------------
        meta_noindex: GenericNoindex | None
        if response.status_code not in SUCCESS_STATUSES:
            # D-20-F. A 404 or a 503 page may well carry a title and a description, and they
            # describe the error, not the page that was selected. Reading them as that page's
            # content would turn an error template into business evidence, so the document is
            # not parsed at all and the status stays the one visible fact about it.
            self._not_assessed_for_document(
                measurements, run_id, source_for, observed_at, NON_SUCCESS_NOT_ASSESSED
            )
            meta_noindex = None
            status = DocumentStatus.NON_SUCCESS_STATUS
        elif media_type_of(response.content_type) not in HTML_MEDIA_TYPES:
            for metric in HTML_METRICS:
                performed(metric, "OBSERVED", "NOT_APPLICABLE")
            meta_noindex = GenericNoindex.NOT_APPLICABLE
            status = DocumentStatus.NOT_A_DOCUMENT
        elif response.undecodable:
            # The response arrived in a content encoding we cannot decode, so we do not hold the
            # document at all. Every element would read as absent, and publishing that would turn
            # a gap in our own capability into a statement about the page.
            self._runtime_error_for_document(measurements, run_id, source_for, observed_at)
            meta_noindex = GenericNoindex.UNASSESSED
            status = DocumentStatus.UNREADABLE
        else:
            try:
                observed = self.read_html(response.body, response.declared_charset)
            except HtmlUnreadable:
                self._runtime_error_for_document(measurements, run_id, source_for, observed_at)
                meta_noindex = GenericNoindex.UNASSESSED
                status = DocumentStatus.UNREADABLE
            else:
                self._document_metrics(
                    measurements, run_id, source_for, observed_at, observed, response
                )
                meta_noindex = _meta_robots_channel(observed, response)
                status = DocumentStatus.READ

        # --- indexability: each channel on its own, and no combined record ----------------
        # The header channel is assessable whenever a response arrived, document or not, which is
        # what keeps a non-HTML response carrying a directive truthfully representable without
        # inventing an HTML observation nobody made.
        for metric, observation in (
            (Metric.META_ROBOTS_GENERIC_NOINDEX_PRESENT, meta_noindex),
            (
                Metric.X_ROBOTS_TAG_GENERIC_NOINDEX_PRESENT,
                x_robots_tag_generic_noindex(response.x_robots_tag),
            ),
        ):
            if observation is None:
                # The meta channel is document content, and a non-2xx document was not read.
                measurements.append(
                    self._not_assessed(
                        run_id, metric, source_for(metric), observed_at, NON_SUCCESS_NOT_ASSESSED
                    )
                )
                continue
            self._noindex(measurements, run_id, source_for, observed_at, metric, observation)

        return measurements, status

    def _noindex(
        self,
        measurements: list[dict[str, Any]],
        run_id: str,
        source_for: Callable[[Metric], str],
        observed_at: str,
        metric: Metric,
        observation: GenericNoindex,
    ) -> None:
        """One channel's observation, stated in the contract's terms.

        Only what a channel actually established becomes a value, and the two ways a channel can
        be closed to us stay apart: a channel that does not apply is a fact about the
        measurement, one we could not assess is a fact about our runtime. Neither becomes a
        ``false``.
        """
        if observation is GenericNoindex.UNASSESSED:
            measurements.append(
                self._not_assessed(run_id, metric, source_for(metric), observed_at, "RUNTIME_ERROR")
            )
            return
        if observation is GenericNoindex.INDETERMINATE:
            assessment = {"collection_mode": "OBSERVED", "result_state": "UNKNOWN"}
            result = None
        elif observation is GenericNoindex.NOT_APPLICABLE:
            assessment = {"collection_mode": "OBSERVED", "result_state": "NOT_APPLICABLE"}
            result = None
        else:
            assessment = {"collection_mode": "OBSERVED", "result_state": "KNOWN"}
            result = {
                "value_type": "BOOLEAN",
                "boolean_value": observation is GenericNoindex.PRESENT,
            }
        measurements.append(
            self._record(run_id, metric, source_for(metric), observed_at, assessment, result)
        )

    def _runtime_error_for_document(
        self,
        measurements: list[dict[str, Any]],
        run_id: str,
        source_for: Callable[[Metric], str],
        observed_at: str,
    ) -> None:
        """Record that *we* could not read the document, for every metric that needs one."""
        for metric in HTML_METRICS:
            measurements.append(
                self._not_assessed(run_id, metric, source_for(metric), observed_at, "RUNTIME_ERROR")
            )

    def _not_assessed_for_document(
        self,
        measurements: list[dict[str, Any]],
        run_id: str,
        source_for: Callable[[Metric], str],
        observed_at: str,
        reason: str,
    ) -> None:
        """Record, for every metric that needs a document, that none was assessed and why."""
        for metric in HTML_METRICS:
            measurements.append(
                self._not_assessed(run_id, metric, source_for(metric), observed_at, reason)
            )

    def _document_metrics(
        self,
        measurements: list[dict[str, Any]],
        run_id: str,
        source_for: Callable[[Metric], str],
        observed_at: str,
        observed: HtmlObservations,
        response: PageFetchOutcome,
    ) -> None:
        """Presence and value for each document element, honouring a truncated read."""

        def add(metric: Metric, assessment: dict[str, str], result: dict[str, Any] | None) -> None:
            measurements.append(
                self._record(run_id, metric, source_for(metric), observed_at, assessment, result)
            )

        def presence_and_value(
            present_metric: Metric,
            value_metric: Metric,
            raw: str | None,
            value_type: str,
            to_value: Callable[[str], str | None],
        ) -> None:
            if raw is None and response.truncated:
                # We stopped reading before the end. An element we did not see may well be
                # further down, so "absent" would be a claim the read cannot support.
                add(
                    present_metric, {"collection_mode": "OBSERVED", "result_state": "UNKNOWN"}, None
                )
                add(value_metric, {"collection_mode": "OBSERVED", "result_state": "UNKNOWN"}, None)
                return

            # Presence and value are two independent questions. Conflating them is how a value
            # the contract cannot carry turns into "this page has no title".
            normalised = "" if raw is None else normalise_single_line(raw)
            present = bool(normalised)
            add(
                present_metric,
                {"collection_mode": "OBSERVED", "result_state": "KNOWN"},
                {"value_type": "BOOLEAN", "boolean_value": present},
            )

            if not present:
                add(
                    value_metric,
                    {"collection_mode": "OBSERVED", "result_state": "NOT_APPLICABLE"},
                    None,
                )
                return

            value = to_value(normalised)
            if value is None:
                # Observed, but not representable in this version of the contract. Recording a
                # shortened, coerced or parser-refused value here would publish something the
                # page never said, so the honest result is that this established nothing.
                add(value_metric, {"collection_mode": "OBSERVED", "result_state": "UNKNOWN"}, None)
                return

            member = "url_value" if value_type == "URL" else "text_value"
            add(
                value_metric,
                {"collection_mode": "OBSERVED", "result_state": "KNOWN"},
                {"value_type": value_type, member: value},
            )

        def representable_line(text: str) -> str | None:
            return text if len(text) <= self.max_text_length else None

        def representable_canonical(text: str) -> str | None:
            """The canonical resolved against the final URL, if the contract can carry it.

            Both refusals are site-controlled input and neither may escape as an exception or as
            an invalid document: a value the URL parser will not read raises ``ValueError`` out of
            ``urljoin``, and a value it reads perfectly well may still be outside the shape a
            measurement carries. The bound is the URL contract's own, not the text bound: a
            600-character canonical is representable, and calling it UNKNOWN would be false.
            """
            try:
                resolved = urljoin(response.final_url, text)
            except ValueError:
                return None
            return resolved if is_contract_url(resolved) else None

        presence_and_value(
            Metric.PAGE_TITLE_PRESENT,
            Metric.PAGE_TITLE,
            observed.title,
            "TEXT",
            representable_line,
        )
        presence_and_value(
            Metric.META_DESCRIPTION_PRESENT,
            Metric.META_DESCRIPTION,
            observed.meta_description,
            "TEXT",
            representable_line,
        )
        presence_and_value(
            Metric.CANONICAL_PRESENT,
            Metric.CANONICAL_URL,
            observed.canonical_href,
            "URL",
            representable_canonical,
        )

    # --- document builders ---------------------------------------------------------------

    def _record(
        self,
        run_id: str,
        metric: Metric,
        source_url: str,
        observed_at: str,
        assessment: dict[str, str],
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        document: dict[str, Any] = {
            "schema_version": "1.0.0",
            "run_id": run_id,
            "measurement_id": self.new_id(),
            "metric_id": metric.value,
            "source_url": source_url,
            "observed_at": observed_at,
            "collector": STATIC_PAGE_COLLECTOR,
            "collector_version": STATIC_PAGE_COLLECTOR_VERSION,
            "assessment": assessment,
        }
        if result is not None:
            document["result"] = result
        return document

    def _not_assessed(
        self, run_id: str, metric: Metric, source_url: str, observed_at: str, reason: str
    ) -> dict[str, Any]:
        return self._record(
            run_id, metric, source_url, observed_at, {"not_assessed_reason": reason}
        )

    def _evidence_for(self, measurement: dict[str, Any]) -> dict[str, Any]:
        """Evidence mirroring one measurement, and referencing it.

        Its observation context is read off the measurement it references rather than passed in
        beside it: evidence naming a URL the record it rests on never mentioned is a divergence no
        contract can see. No polarity is ever set — every fact this profile records is an
        observation, and PXAPI-20 emits no judgement about any page.
        """
        return {
            "schema_version": "1.0.0",
            "run_id": measurement["run_id"],
            "evidence_id": self.new_id(),
            "source_url": measurement["source_url"],
            "observed_at": measurement["observed_at"],
            "scenario": SCENARIO_SELECTED_PAGE_STATIC_FETCH,
            "collector": STATIC_PAGE_COLLECTOR,
            "collector_version": STATIC_PAGE_COLLECTOR_VERSION,
            "assessment": dict(measurement["assessment"]),
            "measurement_refs": [measurement["measurement_id"]],
        }
