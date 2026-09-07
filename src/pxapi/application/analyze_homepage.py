"""The one use case: analyse a single homepage and return canonical contract documents.

This is where an observation becomes a record, and therefore where the slice's central rule is
enforced in code as well as in the schemas: **a technical failure is never a finding about the
website.** Every path that could not measure something records *why our process did not
measure it* — a provider failed, a permission was refused, a budget ran out, our runtime broke
— and records no value and no polarity at all. The contracts refuse those members outside
``KNOWN``, so the rule is structural in both places rather than merely intended in one.

Three distinctions do the work, and they are deliberately kept apart:

* **absent** — the page genuinely has no title. A fact about the site, stated as ``KNOWN``.
* **not applicable** — there is no title *value* to read because there is no title, or the
  response was not a document at all. A fact about the measurement, not about the site.
* **unknown** — the assessment ran and established nothing: the text will not fit the contract,
  or the body was truncated before we could have seen the element. Never rendered as absence.

The layer holds no transport and no parser. It is handed a fetcher, a reader, a clock and an id
factory, which is what lets one frozen input produce byte-identical documents on every run.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlsplit

from pxapi.domain.observations import (
    COLLECTOR,
    COLLECTOR_VERSION,
    SCENARIO_HOMEPAGE_FETCH,
    Metric,
    Stage,
    normalise_single_line,
    representable_text,
)
from pxapi.domain.run_state import RunState, transition
from pxapi.ports.html_observation import HtmlObservations, HtmlReader, HtmlUnreadable
from pxapi.ports.page_fetch import (
    FetchFailureKind,
    PageFetcher,
    PageFetchFailure,
    PageFetchOutcome,
)

#: Why our process did not measure, in the contract's closed vocabulary. Every entry names the
#: analysis process; none of them says anything about the subject, which is exactly why this
#: mapping is allowed to exist at all.
NOT_ASSESSED_FOR: dict[FetchFailureKind, str] = {
    FetchFailureKind.BLOCKED_TARGET: "PERMISSION_DENIED",
    FetchFailureKind.DNS_FAILURE: "PROVIDER_FAILURE",
    FetchFailureKind.CONNECTION_FAILURE: "PROVIDER_FAILURE",
    FetchFailureKind.TIMEOUT: "TIMEOUT",
    FetchFailureKind.TOO_MANY_REDIRECTS: "PROVIDER_FAILURE",
    FetchFailureKind.INVALID_REDIRECT: "PROVIDER_FAILURE",
    FetchFailureKind.PROTOCOL_ERROR: "PROVIDER_FAILURE",
}

#: The run-level failure code for each fetch failure. An open token on the run state contract.
RUN_FAILURE_CODE: dict[FetchFailureKind, str] = {
    FetchFailureKind.BLOCKED_TARGET: "TARGET_NOT_PERMITTED",
}
DEFAULT_RUN_FAILURE_CODE = "PAGE_FETCH_FAILED"

#: Media types this slice reads as a document. Anything else is a response we can describe but
#: whose HTML metrics simply do not apply.
HTML_MEDIA_TYPES = frozenset({"text/html", "application/xhtml+xml"})

#: The metrics that can only come from a document.
HTML_METRICS = (
    Metric.PAGE_TITLE_PRESENT,
    Metric.PAGE_TITLE,
    Metric.META_DESCRIPTION_PRESENT,
    Metric.META_DESCRIPTION,
    Metric.CANONICAL_PRESENT,
    Metric.CANONICAL_URL,
)

#: Every metric this slice reports on, in a fixed order so two runs are diff-able.
ALL_METRICS = (
    Metric.HTTP_STATUS,
    Metric.FINAL_URL,
    Metric.CONTENT_TYPE,
    Metric.TRANSPORT_IS_HTTPS,
    Metric.REDIRECT_COUNT,
    *HTML_METRICS,
)


def _instant(moment: datetime) -> str:
    """An RFC 3339 UTC instant with the mandatory Z, to second precision."""
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def media_type_of(content_type: str | None) -> str | None:
    """The bare media type of a Content-Type header, lowercased."""
    if not content_type:
        return None
    return content_type.split(";")[0].strip().lower() or None


def _is_absolute_web_url(value: str) -> bool:
    parts = urlsplit(value)
    return parts.scheme in {"http", "https"} and bool(parts.netloc)


class AnalyzeHomepage:
    """Analyses one homepage under ``PUBLIC_NON_INVASIVE`` and returns contract documents."""

    def __init__(
        self,
        fetcher: PageFetcher,
        read_html: HtmlReader,
        clock: Callable[[], datetime],
        new_id: Callable[[], str],
        max_text_length: int,
    ) -> None:
        self.fetcher = fetcher
        self.read_html = read_html
        self.clock = clock
        self.new_id = new_id
        # Read out of the contract by the caller, never restated here: a bound duplicated in a
        # collector is a bound that can silently disagree with the schema it claims to respect.
        self.max_text_length = max_text_length

    # --- the use case ------------------------------------------------------------------

    def run(self, request: dict[str, Any]) -> dict[str, Any]:
        """Execute one analysis run for an already-validated request document."""
        target_url = request["target_url"]

        state = transition(transition(RunState.CREATED, RunState.QUEUED), RunState.RUNNING)
        started = self.clock()

        fetch_started = self.clock()
        result = self.fetcher.fetch(target_url)
        fetch_finished = self.clock()

        if isinstance(result, PageFetchFailure):
            return self._unmeasured(request, state, started, result, fetch_started, fetch_finished)

        return self._measured(request, state, started, result, fetch_started, fetch_finished)

    # --- nothing was measured ----------------------------------------------------------

    def _unmeasured(
        self,
        request: dict[str, Any],
        state: RunState,
        started: datetime,
        failure: PageFetchFailure,
        fetch_started: datetime,
        fetch_finished: datetime,
    ) -> dict[str, Any]:
        """No response arrived, so every metric records why *we* did not measure it.

        Not one of these documents carries a value or a polarity, and the contracts would
        refuse them if it tried. A timeout cannot become a negative finding here.
        """
        run_id = request["run_id"]
        source_url = request["target_url"]
        reason = NOT_ASSESSED_FOR[failure.kind]
        observed_at = _instant(fetch_finished)

        measurements = [
            self._not_assessed(run_id, metric, source_url, observed_at, reason)
            for metric in ALL_METRICS
        ]
        evidence = [self._evidence_for(m, source_url) for m in measurements]

        final = transition(state, RunState.FAILED)
        return self._envelope(
            request=request,
            run_state=self._run_state(
                run_id,
                final,
                started,
                fetch_finished,
                failure_code=RUN_FAILURE_CODE.get(failure.kind, DEFAULT_RUN_FAILURE_CODE),
            ),
            stages=[self._stage(run_id, Stage.PAGE_FETCH, "FAILED", fetch_started, fetch_finished)],
            measurements=measurements,
            evidence=evidence,
        )

    # --- a response arrived -------------------------------------------------------------

    def _measured(
        self,
        request: dict[str, Any],
        state: RunState,
        started: datetime,
        response: PageFetchOutcome,
        fetch_started: datetime,
        fetch_finished: datetime,
    ) -> dict[str, Any]:
        run_id = request["run_id"]
        source_url = request["target_url"]
        observed_at = _instant(fetch_finished)
        measurements: list[dict[str, Any]] = []

        def known(metric: Metric, mode: str, value_type: str, member: str, value: Any) -> None:
            measurements.append(
                self._record(
                    run_id,
                    metric,
                    source_url,
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
                    source_url,
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
            # Either none was declared, or it will not fit the contract. Either way we have no
            # value we can honestly state, and we state that instead of inventing one.
            performed(Metric.CONTENT_TYPE, "OBSERVED", "UNKNOWN")
        else:
            known(Metric.CONTENT_TYPE, "OBSERVED", "TEXT", "text_value", content_type)

        # --- document facts --------------------------------------------------------------
        media_type = media_type_of(response.content_type)
        if media_type not in HTML_MEDIA_TYPES:
            # Not a document: the HTML metrics do not apply to this subject. That is a fact
            # about the measurement, and deliberately not a complaint about the site.
            for metric in HTML_METRICS:
                performed(metric, "OBSERVED", "NOT_APPLICABLE")
            html_status = "NOT_APPLICABLE"
        elif response.undecodable:
            # The response arrived in a content encoding we cannot decode, so we do not hold
            # the document at all. Every element would read as absent, and publishing that
            # would turn a gap in our own capability into a finding about the site.
            self._runtime_error_for_document(measurements, run_id, source_url, observed_at)
            html_status = "FAILED"
        else:
            try:
                observed = self.read_html(response.body, response.declared_charset)
            except HtmlUnreadable:
                # Our parser failed. That is our runtime, so nothing is asserted about the
                # page: no absence, no value, no polarity.
                self._runtime_error_for_document(measurements, run_id, source_url, observed_at)
                html_status = "FAILED"
            else:
                self._document_metrics(
                    measurements, run_id, source_url, observed_at, observed, response
                )
                html_status = "SUCCEEDED"

        evidence = [self._evidence_for(m, source_url) for m in measurements]
        final = transition(state, RunState.SUCCEEDED)
        stages = [
            self._stage(run_id, Stage.PAGE_FETCH, "SUCCEEDED", fetch_started, fetch_finished),
            self._stage(
                run_id,
                Stage.HTML_OBSERVATION,
                "FAILED" if html_status == "FAILED" else "SUCCEEDED",
                fetch_finished,
                fetch_finished,
            ),
        ]
        return self._envelope(
            request=request,
            run_state=self._run_state(run_id, final, started, fetch_finished),
            stages=stages,
            measurements=measurements,
            evidence=evidence,
        )

    def _runtime_error_for_document(
        self,
        measurements: list[dict[str, Any]],
        run_id: str,
        source_url: str,
        observed_at: str,
    ) -> None:
        """Record that *we* could not read the document, for every metric that needs one."""
        for metric in HTML_METRICS:
            measurements.append(
                self._not_assessed(run_id, metric, source_url, observed_at, "RUNTIME_ERROR")
            )

    def _document_metrics(
        self,
        measurements: list[dict[str, Any]],
        run_id: str,
        source_url: str,
        observed_at: str,
        observed: HtmlObservations,
        response: PageFetchOutcome,
    ) -> None:
        """Presence and value for each document element, honouring a truncated read."""

        def add(metric: Metric, assessment: dict[str, str], result: dict[str, Any] | None) -> None:
            measurements.append(
                self._record(run_id, metric, source_url, observed_at, assessment, result)
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

            # Presence and value are two independent questions, and conflating them is how a
            # value the contract cannot carry turns into "the site has no title". Whether the
            # element is there is decided first, and the bound never enters into it.
            normalised = "" if raw is None else normalise_single_line(raw)
            present = bool(normalised)
            add(
                present_metric,
                {"collection_mode": "OBSERVED", "result_state": "KNOWN"},
                {"value_type": "BOOLEAN", "boolean_value": present},
            )

            if not present:
                # Genuinely absent, or empty once normalised: there is no value to read.
                add(
                    value_metric,
                    {"collection_mode": "OBSERVED", "result_state": "NOT_APPLICABLE"},
                    None,
                )
                return

            value = to_value(normalised) if len(normalised) <= self.max_text_length else None
            if value is None:
                # Observed, but not representable in this version of the contract. Recording
                # a shortened or coerced value here would publish something the site never
                # said, so the honest result is that this established nothing.
                add(value_metric, {"collection_mode": "OBSERVED", "result_state": "UNKNOWN"}, None)
                return

            member = "url_value" if value_type == "URL" else "text_value"
            add(
                value_metric,
                {"collection_mode": "OBSERVED", "result_state": "KNOWN"},
                {"value_type": value_type, member: value},
            )

        presence_and_value(
            Metric.PAGE_TITLE_PRESENT, Metric.PAGE_TITLE, observed.title, "TEXT", lambda t: t
        )
        presence_and_value(
            Metric.META_DESCRIPTION_PRESENT,
            Metric.META_DESCRIPTION,
            observed.meta_description,
            "TEXT",
            lambda t: t,
        )

        def absolute_canonical(text: str) -> str | None:
            # A canonical link may legitimately be relative; resolving it against the final
            # URL is deterministic and is what a browser would do.
            resolved = urljoin(response.final_url, text)
            if not _is_absolute_web_url(resolved) or len(resolved) > 2048:
                return None
            return resolved

        presence_and_value(
            Metric.CANONICAL_PRESENT,
            Metric.CANONICAL_URL,
            observed.canonical_href,
            "URL",
            absolute_canonical,
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
            "collector": COLLECTOR,
            "collector_version": COLLECTOR_VERSION,
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

    def _evidence_for(self, measurement: dict[str, Any], source_url: str) -> dict[str, Any]:
        """Evidence mirroring one measurement, and referencing it.

        No polarity is ever set. Every fact this slice records — a status code, a content type,
        whether a title exists — is an observation, not a judgement, and inventing a good/bad
        verdict for it is precisely what the contract's optional polarity exists to avoid.
        """
        return {
            "schema_version": "1.0.0",
            "run_id": measurement["run_id"],
            "evidence_id": self.new_id(),
            "source_url": source_url,
            "observed_at": measurement["observed_at"],
            "scenario": SCENARIO_HOMEPAGE_FETCH,
            "collector": COLLECTOR,
            "collector_version": COLLECTOR_VERSION,
            "assessment": dict(measurement["assessment"]),
            "measurement_refs": [measurement["measurement_id"]],
        }

    def _run_state(
        self,
        run_id: str,
        state: RunState,
        entered_at: datetime,
        finished_at: datetime,
        failure_code: str | None = None,
    ) -> dict[str, Any]:
        document: dict[str, Any] = {
            "schema_version": "1.0.0",
            "run_id": run_id,
            "state": state.value,
            "entered_at": _instant(entered_at),
            "finished_at": _instant(finished_at),
        }
        if failure_code is not None:
            document["failure"] = {"code": failure_code}
        return document

    def _stage(
        self, run_id: str, stage: Stage, status: str, started: datetime, finished: datetime
    ) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "run_id": run_id,
            "stage_id": stage.value,
            "status": status,
            "started_at": _instant(started),
            "finished_at": _instant(finished),
        }

    @staticmethod
    def _envelope(
        request: dict[str, Any],
        run_state: dict[str, Any],
        stages: list[dict[str, Any]],
        measurements: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """The canonical response: a transport composition of independently valid documents.

        It is deliberately not a registered contract of its own. It adds no analysis meaning —
        every part carries its own ``schema_version`` and validates on its own — and
        registering it would create a second authority beside the contracts it merely carries.
        """
        return {
            "analysis_run_request": request,
            "analysis_run_state": run_state,
            "stage_executions": stages,
            "measurements": measurements,
            "website_evidence": evidence,
        }
