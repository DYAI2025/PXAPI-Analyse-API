"""The discovery use case: one public target in, a site inventory and a census manifest out.

This is where the two PXAPI-19.A contracts become executable. The use case asks a
``SiteDiscoveryPort`` what it observed, turns those observations into a ``site-inventory.v1``
document through the Domain's admission, canonicalisation and classification rules, draws a
deterministic ``CENSUS`` selection from it as a ``sampling-manifest.v1`` document, and returns
both with the run state and stage records that say what happened.

Three rules are enforced here in code as well as in the contracts.

**No origin, no documents.** A bootstrap that established no canonical public origin produces
neither an inventory nor a manifest (D-PXAPI19-PO-006). The run ends ``FAILED`` with a neutral
technical failure code, and nothing is emitted that a reader could take for "this site has no
pages".

**Nothing leaves that the producer cannot stand behind.** Every document is checked against the
contract-semantic rules and this producer's own invariants before it is returned, and a document
that fails is *withheld* — the run fails with a code naming our defect — rather than repaired.

**A technical outcome is never a finding.** The envelope carries no measurement, no evidence,
no finding, no score, no severity and no polarity, and cannot: the two documents are closed
objects that have no such member, and the run state names what our process did. An exhausted
budget, an absent sitemap or a refused redirect is a statement about this analysis.

The layer holds no transport and no parser. It is handed a discovery port, a clock, an id
factory and the selection budgets, which is what lets one frozen discovery input produce
documents whose digests are identical on every run.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from pxapi.domain.acquisition_digests import inventory_digests, manifest_digests
from pxapi.domain.acquisition_semantics import (
    ProducerInvariantViolated,
    SemanticAmbiguity,
    require_emittable_inventory,
    require_emittable_manifest,
)
from pxapi.domain.page_classification import CLASSIFIER, CLASSIFIER_VERSION
from pxapi.domain.run_state import RunState, transition
from pxapi.domain.sampling_policy import (
    POLICY_ID,
    POLICY_VERSION,
    SelectionBudgets,
    SelectionPlan,
    plan_census,
)
from pxapi.domain.site_discovery import (
    DISCOVERY_METHOD,
    DISCOVERY_METHOD_VERSION,
    BootstrapFailure,
    Candidate,
    DiscoveryReport,
    DiscoveryStage,
    admitted_observations,
    assemble_candidates,
    observation_records,
    source_candidate_counts,
)
from pxapi.domain.site_identity import canonical_origin
from pxapi.ports.site_discovery import SiteDiscoveryPort

#: The run-level failure code for each way a bootstrap can fail. Open tokens on the run state
#: contract, each naming our side: ``TARGET_NOT_PERMITTED`` is the token the homepage analysis
#: already uses for the same refusal, so one refusal has one name across both use cases.
BOOTSTRAP_FAILURE_CODE: dict[BootstrapFailure, str] = {
    BootstrapFailure.TARGET_REFUSED: "TARGET_NOT_PERMITTED",
    BootstrapFailure.UNREACHABLE: "SITE_DISCOVERY_TARGET_UNREACHABLE",
    BootstrapFailure.TIMEOUT: "SITE_DISCOVERY_TIMEOUT",
    BootstrapFailure.RUNTIME_ERROR: "SITE_DISCOVERY_RUNTIME_ERROR",
}

#: A provider that reported no origin and no reason is a provider defect, not a site fact.
UNEXPLAINED_BOOTSTRAP_CODE = "SITE_DISCOVERY_BOOTSTRAP_FAILED"

#: This producer built a document it may not emit. Each names a defect in this service.
INVENTORY_WITHHELD_CODE = "SITE_INVENTORY_NOT_EMITTABLE"
MANIFEST_WITHHELD_CODE = "SAMPLING_MANIFEST_NOT_EMITTABLE"

_PRODUCER_REFUSALS = (ProducerInvariantViolated, SemanticAmbiguity, ValueError)


def _instant(moment: datetime) -> str:
    """An RFC 3339 UTC instant with the mandatory Z, to second precision."""
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _candidate_document(candidate: Candidate) -> dict[str, Any]:
    eligibility: dict[str, Any] = {"state": candidate.eligibility.value}
    if candidate.exclusion_reason is not None:
        eligibility["exclusion_reason"] = candidate.exclusion_reason.value
    document: dict[str, Any] = {
        "url_key": candidate.url_key,
        "observed_forms": list(candidate.observed_forms),
        "provenance": list(candidate.provenance),
    }
    if candidate.page_type is not None:
        document["page_type"] = candidate.page_type
    document["eligibility"] = eligibility
    return document


class DiscoverSite:
    """Discovers one site and plans its census, returning canonical contract documents."""

    def __init__(
        self,
        discovery: SiteDiscoveryPort,
        clock: Callable[[], datetime],
        new_id: Callable[[], str],
        budgets: SelectionBudgets,
    ) -> None:
        self.discovery = discovery
        self.clock = clock
        self.new_id = new_id
        self.budgets = budgets

    # --- the use case ------------------------------------------------------------------

    def run(self, request: dict[str, Any]) -> dict[str, Any]:
        """Execute one discovery run for an already-validated request document."""
        run_id = request["run_id"]
        state = transition(transition(RunState.CREATED, RunState.QUEUED), RunState.RUNNING)
        started = self.clock()
        try:
            report = self.discovery.discover(request["target_url"])
        except Exception:
            # The port contract is outcomes, not exceptions. A provider that breaks it is a
            # defect of ours, recorded as our runtime's failure rather than taking the run down.
            report = DiscoveryReport(None, bootstrap_failure=BootstrapFailure.RUNTIME_ERROR)
        discovered = self.clock()

        origin = canonical_origin(report.target_origin) if report.target_origin else None
        if origin is None:
            code = (
                BOOTSTRAP_FAILURE_CODE[report.bootstrap_failure]
                if report.bootstrap_failure is not None
                else UNEXPLAINED_BOOTSTRAP_CODE
            )
            return self._failed(request, state, started, discovered, code, discovery_ok=False)

        try:
            inventory, candidates = self._inventory(run_id, origin, report, discovered)
        except _PRODUCER_REFUSALS:
            return self._failed(
                request, state, started, discovered, INVENTORY_WITHHELD_CODE, discovery_ok=False
            )

        planned = self.clock()
        try:
            manifest = self._manifest(run_id, inventory, origin, candidates, planned)
        except _PRODUCER_REFUSALS:
            return self._failed(
                request,
                state,
                started,
                planned,
                MANIFEST_WITHHELD_CODE,
                discovery_ok=True,
                inventory=inventory,
                discovered=discovered,
            )

        return {
            "analysis_run_request": request,
            "analysis_run_state": self._run_state(
                run_id, transition(state, RunState.SUCCEEDED), started, planned
            ),
            "stage_executions": [
                self._stage(
                    run_id, DiscoveryStage.SITE_DISCOVERY, "SUCCEEDED", started, discovered
                ),
                self._stage(run_id, DiscoveryStage.SAMPLING_PLAN, "SUCCEEDED", discovered, planned),
            ],
            "site_inventory": inventory,
            "sampling_manifest": manifest,
        }

    # --- the two documents ---------------------------------------------------------------

    def _inventory(
        self, run_id: str, origin: str, report: DiscoveryReport, at: datetime
    ) -> tuple[dict[str, Any], tuple[Candidate, ...]]:
        """The ``site-inventory.v1`` document, refused unless this producer may emit it."""
        admitted = admitted_observations(report.observations)
        candidates = assemble_candidates(admitted, origin)
        counts = source_candidate_counts(candidates)

        document: dict[str, Any] = {
            "schema_version": "1.0.0",
            "run_id": run_id,
            "inventory_id": self.new_id(),
            "generated_at": _instant(at),
            "target_origin": origin,
            "discovery_method": DISCOVERY_METHOD,
            "discovery_method_version": DISCOVERY_METHOD_VERSION,
            "classifier": CLASSIFIER,
            "classifier_version": CLASSIFIER_VERSION,
            # Emitted in canonical order, so two runs over one frozen input are byte-identical
            # apart from their envelope — the digest would not need it, a reader diffing two
            # documents does. A duplicated source identity survives this sort and is refused
            # by the semantic gate below rather than silently collapsed.
            "sources": sorted(
                (
                    {
                        "source_id": attempt.source_id,
                        "outcome": attempt.outcome.value,
                        "candidate_count": counts.get(attempt.source_id, 0),
                    }
                    for attempt in report.attempts
                ),
                key=lambda source: source["source_id"],
            ),
            "candidates": [_candidate_document(candidate) for candidate in candidates],
        }
        require_emittable_inventory(document)
        document["input_digest"], document["output_digest"] = inventory_digests(
            document, observation_records(admitted)
        )
        return document, candidates

    def _manifest(
        self,
        run_id: str,
        inventory: dict[str, Any],
        origin: str,
        candidates: tuple[Candidate, ...],
        at: datetime,
    ) -> dict[str, Any]:
        """The ``sampling-manifest.v1`` document, refused unless this producer may emit it."""
        plan = plan_census(candidates, origin, self.budgets)
        document = self._manifest_document(run_id, inventory, plan, at)
        require_emittable_manifest(document, inventory)
        document["input_digest"], document["output_digest"] = manifest_digests(document)
        return document

    def _manifest_document(
        self, run_id: str, inventory: dict[str, Any], plan: SelectionPlan, at: datetime
    ) -> dict[str, Any]:
        document: dict[str, Any] = {
            "schema_version": "1.0.0",
            "run_id": run_id,
            "sampling_manifest_id": self.new_id(),
            "generated_at": _instant(at),
            "inventory_ref": inventory["inventory_id"],
            "inventory_output_digest": inventory["output_digest"],
            "policy_id": POLICY_ID,
            "policy_version": POLICY_VERSION,
        }
        declared = plan.budgets.declared()
        if declared:
            document["budgets"] = declared
        document["mode"] = plan.mode
        document["selection_complete"] = plan.selection_complete
        if plan.incompleteness_cause is not None:
            document["incompleteness"] = {"cause": plan.incompleteness_cause}
        document["selections"] = [
            {
                "url_key": selection.url_key,
                "selection_rank": selection.rank,
                "selection_reason": selection.reason,
                "stratum": selection.stratum,
            }
            for selection in plan.selections
        ]
        document["exclusions"] = [
            {"reason": reason, "candidate_count": count} for reason, count in plan.exclusions
        ]
        return document

    # --- a run that emits less than both documents ---------------------------------------

    def _failed(
        self,
        request: dict[str, Any],
        state: RunState,
        started: datetime,
        finished: datetime,
        code: str,
        *,
        discovery_ok: bool,
        inventory: dict[str, Any] | None = None,
        discovered: datetime | None = None,
    ) -> dict[str, Any]:
        """A ``FAILED`` run naming our defect or our limitation, and nothing about the site.

        A valid inventory that was already emitted stays in the envelope when only the plan
        failed: withholding it would hide a document this run did stand behind.
        """
        run_id = request["run_id"]
        if discovery_ok and discovered is not None:
            stages = [
                self._stage(
                    run_id, DiscoveryStage.SITE_DISCOVERY, "SUCCEEDED", started, discovered
                ),
                self._stage(run_id, DiscoveryStage.SAMPLING_PLAN, "FAILED", discovered, finished),
            ]
        else:
            stages = [
                self._stage(run_id, DiscoveryStage.SITE_DISCOVERY, "FAILED", started, finished)
            ]
        envelope: dict[str, Any] = {
            "analysis_run_request": request,
            "analysis_run_state": self._run_state(
                run_id, transition(state, RunState.FAILED), started, finished, failure_code=code
            ),
            "stage_executions": stages,
        }
        if inventory is not None:
            envelope["site_inventory"] = inventory
        return envelope

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

    @staticmethod
    def _stage(
        run_id: str, stage: DiscoveryStage, status: str, started: datetime, finished: datetime
    ) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "run_id": run_id,
            "stage_id": stage.value,
            "status": status,
            "started_at": _instant(started),
            "finished_at": _instant(finished),
        }
