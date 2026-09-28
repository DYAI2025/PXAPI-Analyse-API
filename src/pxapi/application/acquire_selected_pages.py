"""Acquiring every page a sampling manifest selected, over static HTTP, and nothing else.

This is the PXAPI-20.B runtime: ``Target -> SiteInventory -> SamplingManifest -> admission ->
PageFetchPort -> PageAcquisitionRecord(STATIC_HTTP) -> MeasurementRecords -> WebsiteEvidence``.
Discovery and planning are the existing ``DiscoverSite`` use case, unchanged; each page is
fetched through the existing ``PageFetcher`` port and observed by the generic
``StaticPageObserver``. What this module adds is the orchestration between them, and it holds
five rules.

**The manifest is the population.** The declared ``max_selected_pages`` budget is the
manifest's own selection budget (D-20-A) and this module applies no second one: every selected
Page Ref is attempted exactly once, in selection-rank order, and represented by exactly one
acquisition record. Whether the selection itself covered the site is the manifest's statement —
``selection_complete`` and ``incompleteness`` — which travels unchanged in the envelope.

**Admission comes before any fetch.** The bound manifest and inventory are checked by the
Domain's admission gate first (D-20-B): an unknown or duplicated Page Ref, a broken binding or a
digest that does not reproduce refuses the whole selection before a single request is made, and
the run fails naming our defect.

**A site outcome is contained per page and stays neutral** (D-20-D, D-20-F). A 4xx or 5xx is a
received response whose status is measured; a timeout, a DNS failure, a refused target, a bad
redirect, a truncated or undecodable body and a parser failure each become one truthful record
whose observations are ``NOT_ASSESSED`` or withheld. One page's outcome never touches a
sibling's records, and none of them is a finding, a score or a polarity — this module emits
none of those at all.

**Our own defects stay visible.** A fetch port that raises or returns something other than a
``PageFetchOutcome`` or ``PageFetchFailure``, an observation that raises, and a set of page
documents that breaks a producer invariant each fail the run with a code naming this service,
and every page document is withheld rather than emitted in part. None of them is laundered into
a neutral page outcome: the port contract is outcomes, so a breach of it is not a site fact.

**A response URL with no identity is not a received response we can record.** The contract
requires ``final_url_key`` on every received response, and a redirect can end at a URL the
Domain's canonicalisation refuses (a raw backslash, a malformed escape). Such a redirect is
recorded as ``INVALID_REDIRECT`` — a redirect this service could not carry — rather than as a
received response with an invented identity, or as a run failure a site could trigger at will.

The layer holds no transport and no parser, and it reads no clock and issues no identity it was
not handed, which is what lets one frozen acquisition input serialise to the same result twice.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, Final, Protocol

from pxapi.application.observe_static_page import PageObservation, StaticPageObserver
from pxapi.domain.page_acquisition import (
    ACQUISITION_METHOD,
    ACQUISITION_METHOD_VERSION,
    OBSERVATION_MODE_STATIC_HTTP,
    AcquisitionOutcome,
    SelectionNotAdmissible,
    admitted_page_refs,
    body_digest,
    require_emittable_acquisition,
)
from pxapi.domain.run_state import RunState, transition
from pxapi.domain.site_identity import canonical_url_key
from pxapi.ports.page_fetch import (
    FetchFailureKind,
    PageFetcher,
    PageFetchFailure,
    PageFetchOutcome,
)

#: The stage this module executes. ``stage_id`` is an open token on its contract.
PAGE_ACQUISITION_STAGE: Final = "PAGE_ACQUISITION"

#: The bound selection failed admission; nothing was fetched. A defect of this service.
SELECTION_NOT_ADMISSIBLE_CODE: Final = "SAMPLING_MANIFEST_NOT_ADMISSIBLE"

#: This service built page documents it may not emit, and withheld all of them.
ACQUISITION_WITHHELD_CODE: Final = "PAGE_ACQUISITION_NOT_EMITTABLE"

#: The envelope members this module adds. ``page_acquisitions`` is the member the Domain's
#: invariants address as ``RECORDS_POINTER``.
PAGE_DOCUMENT_MEMBERS: Final[tuple[str, ...]] = (
    "page_acquisitions",
    "measurements",
    "website_evidence",
)


class PortContractBreach(Exception):
    """The fetch port returned something that is neither outcome shape. A defect of ours."""


class SiteDiscoveryUseCase(Protocol):
    """What this module needs from discovery: one request in, the discovery envelope out."""

    def run(self, request: dict[str, Any]) -> dict[str, Any]: ...


def _instant(moment: datetime) -> str:
    """An RFC 3339 UTC instant with the mandatory Z, to second precision."""
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


class AcquireSelectedPages:
    """Discovers one site, plans its selection, and acquires every selected page once."""

    def __init__(
        self,
        discover: SiteDiscoveryUseCase,
        fetcher: PageFetcher,
        observer: StaticPageObserver,
        clock: Callable[[], datetime],
        new_id: Callable[[], str],
    ) -> None:
        self.discover = discover
        self.fetcher = fetcher
        self.observer = observer
        self.clock = clock
        self.new_id = new_id

    # --- the use case ------------------------------------------------------------------

    def run(self, request: dict[str, Any]) -> dict[str, Any]:
        """Execute one acquisition run for an already-validated request document."""
        envelope = self.discover.run(request)
        if envelope.get("analysis_run_state", {}).get("state") != RunState.SUCCEEDED.value:
            # Discovery or planning did not produce a selection, and said why. There is nothing
            # to acquire, and nothing about any page may be stated.
            return envelope

        run_id = request["run_id"]
        started = self.clock()
        manifest = envelope.get("sampling_manifest")
        try:
            page_refs = admitted_page_refs(manifest, envelope.get("site_inventory"), run_id)
        except SelectionNotAdmissible:
            return self._failed(
                envelope, started, started, SELECTION_NOT_ADMISSIBLE_CODE, keep_manifest=False
            )

        records: list[dict[str, Any]] = []
        measurements: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        try:
            for url_key in page_refs:
                record, observation = self._acquire(run_id, manifest, url_key)
                records.append(record)
                measurements.extend(observation.measurements)
                evidence.extend(observation.evidence)
            require_emittable_acquisition(records, manifest, measurements, evidence)
        except Exception:
            # Every site outcome was already contained inside ``_acquire``; what reaches here
            # is ours — a fetch port that raised or broke its contract, an observation that
            # raised, or a document set we may not emit.
            return self._failed(envelope, started, self.clock(), ACQUISITION_WITHHELD_CODE)

        finished = self.clock()
        return {
            "analysis_run_request": envelope["analysis_run_request"],
            "analysis_run_state": self._run_state(
                envelope, RunState.SUCCEEDED, finished, failure_code=None
            ),
            "stage_executions": [
                *envelope["stage_executions"],
                self._stage(run_id, "SUCCEEDED", started, finished),
            ],
            "site_inventory": envelope["site_inventory"],
            "sampling_manifest": manifest,
            "page_acquisitions": records,
            "measurements": measurements,
            "website_evidence": evidence,
        }

    # --- one selected page ---------------------------------------------------------------

    def _acquire(
        self, run_id: str, manifest: dict[str, Any], url_key: str
    ) -> tuple[dict[str, Any], PageObservation]:
        """One attempt at one selected page, its record and its observation."""
        acquisition_id = self.new_id()
        # The port contract is outcomes, not exceptions: an exception out of the fetcher, or a
        # value that is neither outcome shape, is a defect of this service and propagates to
        # ``run``, which fails the run and withholds every page document (D-20-D).
        result: Any = self.fetcher.fetch(url_key)
        if not isinstance(result, PageFetchOutcome | PageFetchFailure):
            raise PortContractBreach(type(result).__name__)
        acquired_at = _instant(self.clock())

        final_url_key = None
        if isinstance(result, PageFetchOutcome):
            final_url_key = canonical_url_key(result.final_url)
            if final_url_key is None:
                result = PageFetchFailure(FetchFailureKind.INVALID_REDIRECT)

        outcome = (
            AcquisitionOutcome.RESPONSE_RECEIVED
            if isinstance(result, PageFetchOutcome)
            else AcquisitionOutcome(result.kind.value)
        )
        observation = self.observer.observe(run_id, url_key, result, acquired_at)

        document: dict[str, Any] = {
            "schema_version": "1.0.0",
            "run_id": run_id,
            "acquisition_id": acquisition_id,
            "sampling_manifest_ref": manifest["sampling_manifest_id"],
            "sampling_manifest_output_digest": manifest["output_digest"],
            "url_key": url_key,
            "observation_mode": OBSERVATION_MODE_STATIC_HTTP,
            "acquisition_method": ACQUISITION_METHOD,
            "acquisition_method_version": ACQUISITION_METHOD_VERSION,
            "acquired_at": acquired_at,
            "acquisition_outcome": outcome.value,
        }
        if isinstance(result, PageFetchOutcome):
            document["http_status"] = result.status_code
            document["final_url_key"] = final_url_key
            document["redirect_count"] = result.redirect_count
            document["body_truncated"] = result.truncated
            document["body_decoded"] = not result.undecodable
            if not result.undecodable:
                document["body_digest"] = body_digest(result.body)
        document["measurement_refs"] = [item["measurement_id"] for item in observation.measurements]
        if observation.withheld_reason is not None:
            document["measurements_withheld_reason"] = observation.withheld_reason
        return document, observation

    # --- a run that emits no page documents ----------------------------------------------

    def _failed(
        self,
        envelope: dict[str, Any],
        started: datetime,
        finished: datetime,
        code: str,
        *,
        keep_manifest: bool = True,
    ) -> dict[str, Any]:
        """A ``FAILED`` run naming our defect, with every page document withheld.

        The inventory stays: it was emitted by a stage that succeeded and withholding it would
        hide a document this run does stand behind. The manifest stays unless it is the
        document that failed admission.
        """
        run_id = envelope["analysis_run_state"]["run_id"]
        failed: dict[str, Any] = {
            "analysis_run_request": envelope["analysis_run_request"],
            "analysis_run_state": self._run_state(
                envelope, RunState.FAILED, finished, failure_code=code
            ),
            "stage_executions": [
                *envelope["stage_executions"],
                self._stage(run_id, "FAILED", started, finished),
            ],
        }
        if "site_inventory" in envelope:
            failed["site_inventory"] = envelope["site_inventory"]
        if keep_manifest and "sampling_manifest" in envelope:
            failed["sampling_manifest"] = envelope["sampling_manifest"]
        return failed

    @staticmethod
    def _run_state(
        envelope: dict[str, Any],
        target: RunState,
        finished: datetime,
        failure_code: str | None,
    ) -> dict[str, Any]:
        """The run's terminal state once acquisition ended.

        ``entered_at`` is the discovery run state's own, unchanged, so the existing timing
        pattern is reproduced rather than diverged from inside one release (D-20-G).
        """
        discovered = envelope["analysis_run_state"]
        document: dict[str, Any] = {
            "schema_version": "1.0.0",
            "run_id": discovered["run_id"],
            "state": transition(RunState.RUNNING, target).value,
            "entered_at": discovered["entered_at"],
            "finished_at": _instant(finished),
        }
        if failure_code is not None:
            document["failure"] = {"code": failure_code}
        return document

    @staticmethod
    def _stage(run_id: str, status: str, started: datetime, finished: datetime) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "run_id": run_id,
            "stage_id": PAGE_ACQUISITION_STAGE,
            "status": status,
            "started_at": _instant(started),
            "finished_at": _instant(finished),
        }
