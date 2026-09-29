"""PXAPI-25 final validation repair: the submitted request, and the run's lifecycle.

Two gaps an independent review confirmed at ``73d1d7b``, each pinned here by a counterexample
that the validator accepted before the repair.

**Target binding.** A receipt attests to the request that was *submitted*, not merely to a run
identity and a budget. The multi-page producer copies the submitted request into the envelope
unchanged (``DiscoverSite.run`` emits ``"analysis_run_request": request``), so the only request
document it can emit is the submitted one, member for member. The oracle is that identity — no
new URL normalisation is invented, and a spelling the producer would never have written (upper-
case host, a dropped slash) is therefore not the submitted request either.

**Lifecycle coherence.** A schema-valid set of members is not yet a run this service could have
produced. The multi-page orchestration (``DiscoverSite`` then ``AcquireSelectedPages``) emits one
stage history and one set of members per outcome; ``pxapi.application.run_lifecycle`` states that
table, and every genuine producer path is pinned against it below, so the table cannot drift from
the producer without a test going red.

Neutrality is re-proved alongside: every genuine technical outcome still validates without a
single ``FAIL`` reason.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from pxapi.application import discover_site
from pxapi.domain.run_validation import REASONS, GateFamily, GateState
from pxapi.domain.sampling_policy import SelectionPlan
from pxapi.domain.site_discovery import (
    BootstrapFailure,
    DiscoveryObservation,
    DiscoveryReport,
    SourceAttempt,
    SourceOutcome,
)
from pxapi.ports.page_fetch import FetchFailureKind, PageFetchFailure
from tests.application.run_fixtures import (
    FULL_BUDGET,
    acquired,
    all_codes,
    codes,
    states,
    tampered,
    validate,
)
from tests.application.test_acquire_selected_pages import (
    ORIGIN,
    PAGE_A,
    PAGE_B,
    REQUEST,
    FakeFetcher,
    build,
)
from tests.contracts.support import CONTRACTS

F = GateFamily
FAIL_CODES = {code.value for code, spec in REASONS.items() if spec.effect is GateState.FAIL}

#: A second, contract-valid public target: the run below was produced for ``ORIGIN``.
OTHER_TARGET = "https://b.example/"


def _reasons(receipt: dict[str, Any], family: GateFamily) -> list[dict[str, str]]:
    return receipt["gates"][family.value]["reasons"]


def _producer_rules(receipt: dict[str, Any]) -> set[str]:
    return {
        item.get("rule", "")
        for item in _reasons(receipt, F.CANONICAL_VALIDITY)
        if item["code"] == "PRODUCER_INVARIANT_BROKEN"
    }


# === Finding A — the receipt is bound to the submitted request ============================


def test_canary_the_genuine_run_passes_its_input_gate() -> None:
    receipt = validate(acquired())
    assert REQUEST["target_url"] == ORIGIN
    assert receipt["gates"]["INPUT_CONTRACT"] == {"state": "PASS", "reasons": []}


def test_a_canonical_request_for_another_target_cannot_pass_the_input_gate() -> None:
    """Submitted target A, canonical request target B, same run id, same budget."""
    envelope = tampered(
        acquired(), lambda e: e["analysis_run_request"].update(target_url=OTHER_TARGET)
    )
    assert CONTRACTS.validate("analysis-run-request", envelope["analysis_run_request"]) == ()
    receipt = validate(envelope)
    assert receipt["gates"]["INPUT_CONTRACT"]["state"] == "FAIL"
    assert {
        "code": "REQUEST_NOT_BOUND_TO_RUN",
        "pointer": "/analysis_run_request/target_url",
    } in _reasons(receipt, F.INPUT_CONTRACT)
    assert receipt["overall_state"] == "FAIL"
    assert OTHER_TARGET not in json.dumps(receipt), "a pointer names the member, never its value"


@pytest.mark.parametrize(
    "spelling",
    ["https://EXAMPLE.com/", "https://example.com", "https://example.com:443/"],
    ids=["uppercase-host", "no-trailing-slash", "default-port"],
)
def test_a_respelled_target_is_not_the_submitted_request(spelling: str) -> None:
    """Normalisation control: the producer never rewrites the request it was handed, so a
    spelling of the same origin that nobody submitted is not the submitted document either."""
    envelope = tampered(acquired(), lambda e: e["analysis_run_request"].update(target_url=spelling))
    assert CONTRACTS.validate("analysis-run-request", envelope["analysis_run_request"]) == ()
    receipt = validate(envelope)
    assert _reasons(receipt, F.INPUT_CONTRACT) == [
        {"code": "REQUEST_NOT_BOUND_TO_RUN", "pointer": "/analysis_run_request/target_url"}
    ]


def test_any_other_member_that_was_not_submitted_is_named() -> None:
    envelope = tampered(acquired(), lambda e: e["analysis_run_request"].update(request_id="req-x"))
    receipt = validate(envelope)
    assert _reasons(receipt, F.INPUT_CONTRACT) == [
        {"code": "REQUEST_NOT_BOUND_TO_RUN", "pointer": "/analysis_run_request/request_id"}
    ]


def test_member_order_is_not_identity() -> None:
    """Positive control: the same members in another order are the same document."""

    def reorder(envelope: dict[str, Any]) -> None:
        request = envelope["analysis_run_request"]
        envelope["analysis_run_request"] = dict(reversed(list(request.items())))

    receipt = validate(tampered(acquired(), reorder))
    assert receipt["gates"]["INPUT_CONTRACT"] == {"state": "PASS", "reasons": []}


def _credential_run() -> dict[str, Any]:
    request = dict(REQUEST, target_url="https://operator:s3cr3t@example.com/")
    envelope = build(FakeFetcher(), FULL_BUDGET).run(request)
    assert "analysis_run_request" not in envelope, "canary: the producer withheld the request"
    return envelope


def test_a_withheld_request_is_exempt_only_when_the_submitted_target_carried_credentials() -> None:
    """A clean target was submitted; the documents claim it was refused for credentials and
    withhold the request. The exemption would attest to a refusal that never applied."""
    receipt = validate(_credential_run())  # validated against the clean submitted REQUEST
    assert codes(receipt, F.INPUT_CONTRACT) == ["REQUEST_MISSING"]
    assert receipt["overall_state"] == "FAIL"


# === Finding B — the run's lifecycle is coherent ============================================


def _stages(envelope: dict[str, Any]) -> list[tuple[str, str]]:
    return [(item["stage_id"], item["status"]) for item in envelope["stage_executions"]]


def test_canary_the_genuine_succeeded_run_has_three_succeeded_stages() -> None:
    envelope = acquired()
    assert _stages(envelope) == [
        ("SITE_DISCOVERY", "SUCCEEDED"),
        ("SAMPLING_PLAN", "SUCCEEDED"),
        ("PAGE_ACQUISITION", "SUCCEEDED"),
    ]
    assert validate(envelope)["overall_state"] == "PASS"


@pytest.mark.parametrize(
    "change",
    [
        lambda e: e.__setitem__("stage_executions", []),
        lambda e: e["stage_executions"].pop(),
        lambda e: e["stage_executions"][2].update(status="FAILED"),
        lambda e: e["stage_executions"][1].update(status="CANCELLED"),
        lambda e: e["stage_executions"].reverse(),
        lambda e: e["stage_executions"].append(dict(e["stage_executions"][2])),
    ],
    ids=[
        "no-history",
        "acquisition-missing",
        "acquisition-failed",
        "plan-cancelled",
        "out-of-order",
        "duplicated-stage",
    ],
)
def test_a_succeeded_run_without_its_succeeded_stage_history_fails(change: Any) -> None:
    envelope = tampered(acquired(), change)
    receipt = validate(envelope)
    assert "stage_history_follows_run_outcome" in _producer_rules(receipt), _reasons(
        receipt, F.CANONICAL_VALIDITY
    )
    assert receipt["overall_state"] == "FAIL"


def _stale_page_documents(envelope: dict[str, Any]) -> None:
    """Copy a succeeded run's selection and page documents into a failed run of the same id."""
    succeeded = acquired()
    for name in (
        "site_inventory",
        "sampling_manifest",
        "page_acquisitions",
        "measurements",
        "website_evidence",
    ):
        envelope[name] = succeeded[name]


def test_a_technically_failed_run_carrying_page_documents_fails() -> None:
    failed = acquired(
        discovery_report=DiscoveryReport(None, bootstrap_failure=BootstrapFailure.TIMEOUT)
    )
    genuine = validate(failed)
    assert genuine["overall_state"] == "BLOCKED" and not (all_codes(genuine) & FAIL_CODES)

    receipt = validate(tampered(failed, _stale_page_documents))
    assert "member_follows_run_outcome" in _producer_rules(receipt)
    pointers = {
        item["pointer"]
        for item in _reasons(receipt, F.CANONICAL_VALIDITY)
        if item.get("rule") == "member_follows_run_outcome"
    }
    assert {"/page_acquisitions", "/measurements", "/website_evidence"} <= pointers
    assert receipt["overall_state"] == "FAIL"


def test_a_cancelled_run_carrying_page_documents_fails() -> None:
    envelope = tampered(acquired(), lambda e: e["analysis_run_state"].update(state="CANCELLED"))
    receipt = validate(envelope)
    assert "member_follows_run_outcome" in _producer_rules(receipt)
    assert receipt["overall_state"] == "FAIL"


def test_a_failed_acquisition_that_claims_its_stage_succeeded_fails() -> None:
    fetcher = FakeFetcher({PAGE_A: RuntimeError("port broke its contract")})
    failed = acquired(fetcher)
    assert failed["analysis_run_state"]["failure"]["code"] == "PAGE_ACQUISITION_NOT_EMITTABLE"
    receipt = validate(
        tampered(failed, lambda e: e["stage_executions"][2].update(status="SUCCEEDED"))
    )
    assert "stage_history_follows_run_outcome" in _producer_rules(receipt)


def test_a_failed_plan_that_still_carries_a_manifest_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    failed = _manifest_withheld(monkeypatch)
    manifest = acquired()["sampling_manifest"]
    receipt = validate(tampered(failed, lambda e: e.__setitem__("sampling_manifest", manifest)))
    assert "member_follows_run_outcome" in _producer_rules(receipt)


# --- every genuine producer path is coherent, and stays neutral ------------------------------


def _manifest_withheld(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    real = discover_site.plan_census

    def sampling_planner(*args: Any, **kwargs: Any) -> SelectionPlan:
        plan = real(*args, **kwargs)
        return SelectionPlan(
            "STRATIFIED_SAMPLE",
            plan.selection_complete,
            plan.incompleteness_cause,
            plan.selections,
            plan.exclusions,
            plan.budgets,
        )

    monkeypatch.setattr(discover_site, "plan_census", sampling_planner)
    envelope = acquired()
    monkeypatch.undo()
    assert envelope["analysis_run_state"]["failure"]["code"] == "SAMPLING_MANIFEST_NOT_EMITTABLE"
    return envelope


def _inventory_withheld() -> dict[str, Any]:
    unseeded = DiscoveryReport(
        ORIGIN,
        (DiscoveryObservation(ORIGIN + "kontakt", "SAME_ORIGIN_PAGE_LINKS"),),
        (SourceAttempt("SAME_ORIGIN_PAGE_LINKS", SourceOutcome.USED),),
    )
    envelope = acquired(discovery_report=unseeded)
    assert envelope["analysis_run_state"]["failure"]["code"] == "SITE_INVENTORY_NOT_EMITTABLE"
    return envelope


def _unadmissible() -> dict[str, Any]:
    envelope = acquired(
        tamper=lambda e: e["sampling_manifest"]["selections"][0].__setitem__(
            "url_key", "https://example.com/nowhere"
        )
    )
    assert envelope["analysis_run_state"]["failure"]["code"] == "SAMPLING_MANIFEST_NOT_ADMISSIBLE"
    return envelope


def _genuine_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, tuple[dict[str, Any], dict[str, Any], int]]:
    """``name -> (envelope, submitted request, budget)`` for every outcome the producer emits."""
    paths: dict[str, tuple[dict[str, Any], dict[str, Any], int]] = {
        "succeeded": (acquired(), REQUEST, FULL_BUDGET),
        "succeeded-budget-limited": (acquired(budget=2), REQUEST, 2),
        "succeeded-page-timeouts": (
            acquired(FakeFetcher({PAGE_B: PageFetchFailure(FetchFailureKind.TIMEOUT)})),
            REQUEST,
            FULL_BUDGET,
        ),
        "inventory-withheld": (_inventory_withheld(), REQUEST, FULL_BUDGET),
        "manifest-withheld": (_manifest_withheld(monkeypatch), REQUEST, FULL_BUDGET),
        "selection-not-admissible": (_unadmissible(), REQUEST, FULL_BUDGET),
        "acquisition-withheld": (
            acquired(FakeFetcher({PAGE_A: RuntimeError("boom")})),
            REQUEST,
            FULL_BUDGET,
        ),
        "credential-refused": (
            _credential_run(),
            dict(REQUEST, target_url="https://operator:s3cr3t@example.com/"),
            FULL_BUDGET,
        ),
    }
    for failure in BootstrapFailure:
        envelope = acquired(discovery_report=DiscoveryReport(None, bootstrap_failure=failure))
        paths[f"bootstrap-{failure.value}"] = (envelope, REQUEST, FULL_BUDGET)
    return paths


def test_every_genuine_producer_path_is_lifecycle_coherent(monkeypatch: pytest.MonkeyPatch) -> None:
    from pxapi.application.run_lifecycle import lifecycle_violations

    for name, (envelope, _submitted, _budget) in _genuine_paths(monkeypatch).items():
        assert lifecycle_violations(envelope) == (), name


def test_no_genuine_producer_path_breaks_a_producer_invariant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, (envelope, submitted, budget) in _genuine_paths(monkeypatch).items():
        receipt = validate(envelope, budget=budget, submitted=submitted)
        assert _producer_rules(receipt) == set(), (name, _reasons(receipt, F.CANONICAL_VALIDITY))
        assert codes(receipt, F.INPUT_CONTRACT) in ([], ["REQUEST_WITHHELD_BY_POLICY"]), name


@pytest.mark.parametrize("failure", list(BootstrapFailure), ids=[f.value for f in BootstrapFailure])
def test_technical_failure_is_still_never_a_website_defect(failure: BootstrapFailure) -> None:
    receipt = validate(acquired(discovery_report=DiscoveryReport(None, bootstrap_failure=failure)))
    assert receipt["overall_state"] == "BLOCKED"
    assert all_codes(receipt) & FAIL_CODES == set()
    assert states(receipt)["CANONICAL_VALIDITY"] == "PASS"


def test_the_lifecycle_table_names_the_validator_s_canonical_members() -> None:
    from pxapi.application.run_lifecycle import CANONICAL_MEMBER_NAMES
    from pxapi.application.validate_analysis_run import CANONICAL_MEMBERS

    assert set(CANONICAL_MEMBER_NAMES) == set(CANONICAL_MEMBERS)


def test_every_failure_code_the_producers_emit_has_exactly_one_lifecycle() -> None:
    from pxapi.application.run_lifecycle import LIFECYCLES
    from pxapi.application.validate_analysis_run import (
        PRODUCER_DEFECT_RUN_FAILURES,
        TECHNICAL_RUN_FAILURES,
    )

    failed = {code for state, code in LIFECYCLES if state == "FAILED"}
    assert failed == TECHNICAL_RUN_FAILURES | PRODUCER_DEFECT_RUN_FAILURES
    assert {state for state, _code in LIFECYCLES} == {"SUCCEEDED", "FAILED"}
