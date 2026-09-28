"""Run validation over genuine multi-page runs: every gate, every neutrality rule, determinism.

Every run validated here was produced by the real acquisition runtime over fake ports (see
``run_fixtures``); a defect is planted into a copy afterwards, one named change at a time. Each
receipt is checked against its registered contract and the Domain's receipt rules, so a test that
passes here also proves the receipt it looked at was one the service may emit.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from pxapi.adapters.inbound import acquire_cli
from pxapi.application.discover_site import (
    BOOTSTRAP_FAILURE_CODE,
    INVENTORY_WITHHELD_CODE,
    MANIFEST_WITHHELD_CODE,
    TARGET_NOT_PERMITTED_CODE,
    UNEXPLAINED_BOOTSTRAP_CODE,
)
from pxapi.application.validate_analysis_run import (
    CANONICAL_MEMBERS,
    LIMITING_SOURCE_OUTCOMES,
    PRODUCER_DEFECT_RUN_FAILURES,
    RECEIPT_CONTRACT,
    RECEIPT_FILE,
    TECHNICAL_RUN_FAILURES,
    ValidateAnalysisRun,
    build_artifact_bundle,
    bundle_digest,
    canonical_bytes,
)
from pxapi.domain.run_validation import (
    REASONS,
    GateFamily,
    GateState,
    ReasonCode,
    receipt_rule_violations,
)
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
    RUN_ID,
    acquired,
    all_codes,
    codes,
    receipt_ids,
    states,
    tampered,
    validate,
    validated_at,
)
from tests.application.test_acquire_selected_pages import (
    ORIGIN,
    PAGE_A,
    PAGE_B,
    PAGE_C,
    FakeFetcher,
    html,
    response,
)
from tests.application.test_observe_static_page import UNREPRESENTABLE
from tests.contracts.support import CONTRACTS

F = GateFamily
FAIL_CODES = {code.value for code, spec in REASONS.items() if spec.effect is GateState.FAIL}


def emittable(receipt: dict[str, Any]) -> dict[str, Any]:
    """The receipt, after proving it is one the service may emit."""
    assert CONTRACTS.validate(RECEIPT_CONTRACT, receipt) == ()
    assert receipt_rule_violations(receipt) == ()
    return receipt


def only_failures(receipt: dict[str, Any]) -> set[str]:
    return all_codes(receipt) & FAIL_CODES


# --- a completely valid run -----------------------------------------------------------------


def test_a_completely_valid_run_passes_every_gate() -> None:
    receipt = emittable(validate(acquired()))
    assert receipt["overall_state"] == "PASS"
    assert set(states(receipt).values()) == {"PASS"}
    assert receipt["run_state"] == "SUCCEEDED"
    assert receipt["run_id"] == RUN_ID


def test_the_receipt_binds_the_exact_bundle_it_validated() -> None:
    envelope = acquired()
    bundle = build_artifact_bundle(envelope)
    receipt = emittable(validate(envelope, bundle))
    assert receipt["artifact_bundle_digest"] == bundle_digest(bundle)
    altered = dict(
        bundle, **{"measurement-records.json": bundle["measurement-records.json"] + b" "}
    )
    assert bundle_digest(altered) != receipt["artifact_bundle_digest"]


def test_validation_never_changes_analysis_truth() -> None:
    envelope = acquired(budget=2)
    before = copy.deepcopy(envelope)
    bundle = build_artifact_bundle(envelope)
    frozen = dict(bundle)
    validate(envelope, bundle, budget=2)
    assert envelope == before
    assert bundle == frozen


#: Site-controlled text that decodes to markup: the page writes entities, the parser hands us the
#: characters. This is the realistic injection vector — a raw tag inside ``<title>`` never
#: reaches a measurement as a tag at all.
HOSTILE_TITLE_HTML = "&lt;script&gt;alert(1)&lt;/script&gt; Kanzlei Titel"
HOSTILE_TITLE_TEXT = "<script>alert(1)</script> Kanzlei Titel"


def test_the_receipt_carries_no_website_derived_value() -> None:
    """A receipt is tokens, locations, identities and digests; a page title never reaches it."""
    fetcher = FakeFetcher({PAGE_A: response(PAGE_A, body=html(HOSTILE_TITLE_HTML))})
    envelope = acquired(fetcher)
    titles = [m.get("result", {}).get("text_value") for m in envelope["measurements"]]
    assert HOSTILE_TITLE_TEXT in titles, "canary: the hostile text must reach the documents"
    receipt = json.dumps(emittable(validate(envelope)))
    assert "Kanzlei" not in receipt
    assert "script" not in receipt


# --- SUCCEEDED is not PASS ------------------------------------------------------------------


def test_a_succeeded_run_with_a_budget_limited_selection_is_blocked_not_passed() -> None:
    receipt = emittable(validate(acquired(budget=2), budget=2))
    assert receipt["run_state"] == "SUCCEEDED"
    assert receipt["overall_state"] == "BLOCKED"
    assert codes(receipt, F.ACQUISITION_COMPLETENESS) == ["SELECTION_INCOMPLETE"]


def test_an_incomplete_selection_is_never_a_failure() -> None:
    receipt = emittable(validate(acquired(budget=1), budget=1))
    assert only_failures(receipt) == set()
    assert states(receipt)[F.ACQUISITION_COMPLETENESS] == "BLOCKED"


@pytest.mark.parametrize("kind", list(FetchFailureKind), ids=[k.value for k in FetchFailureKind])
def test_a_technical_page_outcome_blocks_and_never_fails(kind: FetchFailureKind) -> None:
    fetcher = FakeFetcher({PAGE_B: PageFetchFailure(kind)})
    receipt = emittable(validate(acquired(fetcher)))
    assert receipt["run_state"] == "SUCCEEDED"
    assert receipt["overall_state"] == "BLOCKED"
    assert only_failures(receipt) == set()
    assert "PAGE_NOT_ACQUIRED" in codes(receipt, F.ACQUISITION_COMPLETENESS)
    assert codes(receipt, F.EVIDENCE_COVERAGE) == ["PAGE_EVIDENCE_NOT_ASSESSED"]


@pytest.mark.parametrize("status", [404, 500, 503])
def test_a_non_2xx_page_is_a_received_response_whose_document_is_missing_evidence(
    status: int,
) -> None:
    fetcher = FakeFetcher({PAGE_C: response(PAGE_C, status=status)})
    receipt = emittable(validate(acquired(fetcher)))
    assert only_failures(receipt) == set()
    assert codes(receipt, F.ACQUISITION_COMPLETENESS) == []
    assert codes(receipt, F.EVIDENCE_COVERAGE) == ["PAGE_EVIDENCE_NOT_ASSESSED"]


def test_a_truncated_and_an_undecodable_body_block_the_acquisition_gate() -> None:
    fetcher = FakeFetcher(
        {
            PAGE_A: response(PAGE_A, truncated=True),
            PAGE_B: response(PAGE_B, undecodable=True),
        }
    )
    receipt = emittable(validate(acquired(fetcher)))
    assert only_failures(receipt) == set()
    reasons = receipt["gates"][F.ACQUISITION_COMPLETENESS]["reasons"]
    assert {(r["code"], r["pointer"]) for r in reasons} == {
        ("PAGE_BODY_TRUNCATED", "/page_acquisitions/1/body_truncated"),
        ("PAGE_BODY_NOT_DECODED", "/page_acquisitions/2/body_decoded"),
    }


def test_an_assessment_that_established_nothing_is_missing_evidence() -> None:
    fetcher = FakeFetcher({PAGE_A: response(PAGE_A, content_type="")})
    receipt = emittable(validate(acquired(fetcher)))
    assert "PAGE_EVIDENCE_UNKNOWN" in codes(receipt, F.EVIDENCE_COVERAGE)
    assert only_failures(receipt) == set()


def test_a_limited_discovery_source_is_a_stated_limitation() -> None:
    limited = DiscoveryReport(
        target_origin=ORIGIN,
        observations=(
            DiscoveryObservation(ORIGIN, "CANONICAL_SEED"),
            DiscoveryObservation(PAGE_A, "SITEMAP"),
        ),
        attempts=(
            SourceAttempt("CANONICAL_SEED", SourceOutcome.USED),
            SourceAttempt("SITEMAP", SourceOutcome.TIMEOUT),
        ),
    )
    receipt = emittable(validate(acquired(discovery_report=limited, budget=2), budget=2))
    assert codes(receipt, F.UNRESOLVED_CONFLICTS_LIMITATIONS) == ["DISCOVERY_SOURCE_LIMITED"]
    assert only_failures(receipt) == set()


def test_an_unresolved_conflict_blocks_and_is_not_a_failure() -> None:
    def conflict(envelope: dict[str, Any]) -> None:
        measurement = envelope["measurements"][0]
        measurement["assessment"] = {"collection_mode": "OBSERVED", "result_state": "CONFLICT"}
        measurement.pop("result", None)
        for evidence in envelope["website_evidence"]:
            if measurement["measurement_id"] in evidence["measurement_refs"]:
                evidence["assessment"] = dict(measurement["assessment"])

    envelope = tampered(acquired(), conflict)
    receipt = emittable(validate(envelope))
    assert set(codes(receipt, F.UNRESOLVED_CONFLICTS_LIMITATIONS)) == {"UNRESOLVED_CONFLICT"}
    assert only_failures(receipt) == set()


# --- technical run failures are neutral -------------------------------------------------------


@pytest.mark.parametrize("failure", list(BootstrapFailure), ids=[f.value for f in BootstrapFailure])
def test_a_run_that_failed_technically_is_blocked_never_failed_or_passed(
    failure: BootstrapFailure,
) -> None:
    envelope = acquired(discovery_report=DiscoveryReport(None, bootstrap_failure=failure))
    assert envelope["analysis_run_state"]["state"] == "FAILED"
    receipt = emittable(validate(envelope))
    assert receipt["overall_state"] == "BLOCKED"
    assert only_failures(receipt) == set()
    assert codes(receipt, F.ACQUISITION_COMPLETENESS) == ["RUN_FAILED_TECHNICALLY"]
    for family in (F.EVIDENCE_COVERAGE, F.UNRESOLVED_CONFLICTS_LIMITATIONS):
        assert receipt["gates"][family]["state"] == "NOT_APPLICABLE"
        assert codes(receipt, family) == ["RUN_EMITTED_NO_PAGE_DOCUMENTS"]


def test_a_run_that_failed_on_our_own_producer_defect_fails_validation() -> None:
    def unadmissible(envelope: dict[str, Any]) -> None:
        envelope["sampling_manifest"]["selections"][0]["url_key"] = "https://example.com/nowhere"

    envelope = acquired(tamper=unadmissible)
    assert envelope["analysis_run_state"]["failure"]["code"] == "SAMPLING_MANIFEST_NOT_ADMISSIBLE"
    receipt = emittable(validate(envelope))
    assert receipt["overall_state"] == "FAIL"
    assert codes(receipt, F.ACQUISITION_COMPLETENESS) == ["RUN_FAILED_BY_PRODUCER_DEFECT"]


def test_a_failure_code_nobody_classified_is_our_gap_and_fails() -> None:
    def unknown(envelope: dict[str, Any]) -> None:
        envelope["analysis_run_state"]["failure"]["code"] = "SOMETHING_NEW"

    failed = acquired(
        discovery_report=DiscoveryReport(None, bootstrap_failure=BootstrapFailure.TIMEOUT)
    )
    receipt = emittable(validate(tampered(failed, unknown)))
    assert codes(receipt, F.ACQUISITION_COMPLETENESS) == ["RUN_FAILURE_UNCLASSIFIED"]
    assert receipt["overall_state"] == "FAIL"


def test_every_failure_code_the_producers_can_emit_is_classified_exactly_once() -> None:
    emitted = {
        *BOOTSTRAP_FAILURE_CODE.values(),
        UNEXPLAINED_BOOTSTRAP_CODE,
        TARGET_NOT_PERMITTED_CODE,
        INVENTORY_WITHHELD_CODE,
        MANIFEST_WITHHELD_CODE,
        "SAMPLING_MANIFEST_NOT_ADMISSIBLE",
        "PAGE_ACQUISITION_NOT_EMITTABLE",
    }
    assert TECHNICAL_RUN_FAILURES.isdisjoint(PRODUCER_DEFECT_RUN_FAILURES)
    assert emitted == TECHNICAL_RUN_FAILURES | PRODUCER_DEFECT_RUN_FAILURES


def test_no_run_that_did_not_succeed_can_pass() -> None:
    for failure in BootstrapFailure:
        envelope = acquired(discovery_report=DiscoveryReport(None, bootstrap_failure=failure))
        assert validate(envelope)["overall_state"] != "PASS"
    for state in ("CANCELLED", "RUNNING", "QUEUED"):

        def set_state(envelope: dict[str, Any], value: str = state) -> None:
            envelope["analysis_run_state"]["state"] = value

        assert validate(tampered(acquired(), set_state))["overall_state"] != "PASS"


# --- defects of this service FAIL -----------------------------------------------------------


def test_a_broken_canonical_contract_fails_and_names_where() -> None:
    envelope = tampered(acquired(), lambda e: e["measurements"][3].update(schema_version="9.9.9"))
    receipt = emittable(validate(envelope))
    assert receipt["overall_state"] == "FAIL"
    reasons = receipt["gates"][F.CANONICAL_VALIDITY]["reasons"]
    assert {
        "code": "DOCUMENT_CONTRACT_INVALID",
        "pointer": "/measurements/3/schema_version",
        "rule": "const",
    } in reasons


def test_a_member_in_the_wrong_container_fails() -> None:
    envelope = tampered(acquired(), lambda e: e.__setitem__("measurements", {"not": "a list"}))
    receipt = emittable(validate(envelope))
    assert "DOCUMENT_CONTAINER_INVALID" in codes(receipt, F.CANONICAL_VALIDITY)


def test_a_missing_canonical_member_of_a_succeeded_run_fails() -> None:
    envelope = tampered(acquired(), lambda e: e.pop("website_evidence"))
    receipt = emittable(validate(envelope))
    assert "CANONICAL_MEMBER_MISSING" in codes(receipt, F.CANONICAL_VALIDITY)
    assert "LINKED_DOCUMENT_MISSING" in codes(receipt, F.PROVENANCE_LINKAGE)
    assert "BUNDLE_FILE_MISSING" not in codes(receipt, F.ARTIFACT_BUNDLE_VALIDITY)


def test_a_member_that_is_not_canonical_fails() -> None:
    envelope = tampered(acquired(), lambda e: e.__setitem__("diagnostic_findings", []))
    receipt = emittable(validate(envelope))
    assert codes(receipt, F.CANONICAL_VALIDITY) == ["CANONICAL_MEMBER_UNEXPECTED"]


def test_a_contract_semantic_rule_is_checked_beyond_the_schema() -> None:
    def duplicate_rank(envelope: dict[str, Any]) -> None:
        envelope["sampling_manifest"]["selections"][1]["selection_rank"] = 1

    receipt = emittable(validate(tampered(acquired(), duplicate_rank)))
    rules = {
        r.get("rule")
        for r in receipt["gates"][F.CANONICAL_VALIDITY]["reasons"]
        if r["code"] == "DOCUMENT_SEMANTICS_INVALID"
    }
    assert "unique_selection_rank" in rules


def test_a_document_bound_to_another_run_fails_linkage() -> None:
    envelope = tampered(acquired(), lambda e: e["website_evidence"][2].update(run_id="run-other"))
    receipt = emittable(validate(envelope))
    reasons = receipt["gates"][F.PROVENANCE_LINKAGE]["reasons"]
    assert {"code": "RUN_BINDING_BROKEN", "pointer": "/website_evidence/2/run_id"} in reasons


def test_documents_of_the_requested_run_are_checked_against_the_request_not_themselves() -> None:
    receipt = emittable(validate(acquired(), run_id="run-requested-elsewhere"))
    assert "REQUEST_NOT_BOUND_TO_RUN" in codes(receipt, F.INPUT_CONTRACT)
    assert "RUN_BINDING_BROKEN" in codes(receipt, F.PROVENANCE_LINKAGE)


def test_evidence_resting_on_a_measurement_that_does_not_exist_fails_linkage() -> None:
    envelope = tampered(
        acquired(), lambda e: e["website_evidence"][0].update(measurement_refs=["msr-nowhere"])
    )
    receipt = emittable(validate(envelope))
    reasons = receipt["gates"][F.PROVENANCE_LINKAGE]["reasons"]
    assert {
        "code": "ACQUISITION_LINKAGE_BROKEN",
        "pointer": "/website_evidence/0",
        "rule": "evidence_within_one_page",
    } in reasons


def test_a_record_naming_a_measurement_that_does_not_exist_fails_linkage() -> None:
    envelope = tampered(
        acquired(),
        lambda e: e["page_acquisitions"][1]["measurement_refs"].append("msr-nowhere"),
    )
    receipt = emittable(validate(envelope))
    rules = {r.get("rule") for r in receipt["gates"][F.PROVENANCE_LINKAGE]["reasons"]}
    assert "refs_name_a_measurement" in rules


def test_a_measurement_named_by_two_pages_fails_linkage() -> None:
    def shared(envelope: dict[str, Any]) -> None:
        stolen = envelope["page_acquisitions"][0]["measurement_refs"][0]
        envelope["page_acquisitions"][1]["measurement_refs"].append(stolen)

    receipt = emittable(validate(tampered(acquired(), shared)))
    rules = {r.get("rule") for r in receipt["gates"][F.PROVENANCE_LINKAGE]["reasons"]}
    assert "measurement_owned_once" in rules


def test_a_duplicated_identifier_fails_linkage() -> None:
    def duplicate(envelope: dict[str, Any]) -> None:
        envelope["website_evidence"][1]["evidence_id"] = envelope["website_evidence"][0][
            "evidence_id"
        ]

    receipt = emittable(validate(tampered(acquired(), duplicate)))
    reasons = receipt["gates"][F.PROVENANCE_LINKAGE]["reasons"]
    assert {"code": "DUPLICATE_IDENTIFIER", "pointer": "/website_evidence/1/evidence_id"} in reasons


def test_a_manifest_whose_digest_does_not_reproduce_fails_linkage() -> None:
    def stale(envelope: dict[str, Any]) -> None:
        envelope["sampling_manifest"]["output_digest"] = "sha256:" + "0" * 64

    receipt = emittable(validate(tampered(acquired(), stale)))
    reasons = receipt["gates"][F.PROVENANCE_LINKAGE]["reasons"]
    assert {
        "code": "SELECTION_BINDING_BROKEN",
        "pointer": "/sampling_manifest/output_digest",
        "rule": "manifest_digests_reproduce",
    } in reasons


def test_a_manifest_that_does_not_carry_the_declared_budget_fails_the_input_gate() -> None:
    receipt = emittable(validate(acquired(budget=3), budget=2))
    assert codes(receipt, F.INPUT_CONTRACT) == ["DECLARED_BUDGET_NOT_APPLIED"]
    assert receipt["overall_state"] == "FAIL"


def test_an_invalid_request_document_fails_the_input_gate() -> None:
    envelope = tampered(acquired(), lambda e: e["analysis_run_request"].pop("scan_mode"))
    receipt = emittable(validate(envelope))
    assert "REQUEST_CONTRACT_INVALID" in codes(receipt, F.INPUT_CONTRACT)


def test_a_missing_request_fails_the_input_gate() -> None:
    receipt = emittable(validate(tampered(acquired(), lambda e: e.pop("analysis_run_request"))))
    assert codes(receipt, F.INPUT_CONTRACT) == ["REQUEST_MISSING"]


@pytest.mark.parametrize("declared", [0, -1, True, 2.0, "3"])
def test_a_declared_budget_that_is_not_a_whole_number_of_at_least_one_is_refused(
    declared: Any,
) -> None:
    envelope = acquired()
    with pytest.raises(ValueError):
        ValidateAnalysisRun(CONTRACTS, validated_at, receipt_ids()).run(
            envelope, build_artifact_bundle(envelope), run_id=RUN_ID, declared_budget=declared
        )


# --- the artifact bundle ------------------------------------------------------------------


def _bundle_case(change: Any) -> dict[str, Any]:
    envelope = acquired()
    bundle = build_artifact_bundle(envelope)
    change(bundle)
    return emittable(validate(envelope, bundle))


def test_a_corrupted_bundle_file_fails() -> None:
    def corrupt(bundle: dict[str, bytes]) -> None:
        bundle["sampling-manifest.json"] = bundle["sampling-manifest.json"].replace(
            b"CENSUS", b"CENSUX", 1
        )

    receipt = _bundle_case(corrupt)
    assert codes(receipt, F.ARTIFACT_BUNDLE_VALIDITY) == ["BUNDLE_FILE_DIFFERS_FROM_CANONICAL"]
    assert receipt["overall_state"] == "FAIL"


def test_a_missing_expected_artifact_fails() -> None:
    receipt = _bundle_case(lambda b: b.pop("website-evidence.json"))
    reasons = receipt["gates"][F.ARTIFACT_BUNDLE_VALIDITY]["reasons"]
    assert reasons == [{"code": "BUNDLE_FILE_MISSING", "pointer": "/website-evidence.json"}]


def test_a_truncated_bundle_file_is_not_json_and_fails() -> None:
    def truncate(bundle: dict[str, bytes]) -> None:
        bundle["measurement-records.json"] = bundle["measurement-records.json"][:-20]

    receipt = _bundle_case(truncate)
    assert codes(receipt, F.ARTIFACT_BUNDLE_VALIDITY) == ["BUNDLE_FILE_NOT_JSON"]


def test_a_bundle_carrying_a_receipt_is_not_the_canonical_bundle() -> None:
    """No circularity: the receipt is built from the bundle and can never be part of it."""
    receipt = _bundle_case(lambda b: b.__setitem__(RECEIPT_FILE, b"{}\n"))
    assert codes(receipt, F.ARTIFACT_BUNDLE_VALIDITY) == ["BUNDLE_FILE_UNEXPECTED"]


def test_a_bundle_file_with_a_hostile_name_is_reported_with_a_carriable_pointer() -> None:
    receipt = _bundle_case(lambda b: b.__setitem__("evil\n/../name.json", b"{}"))
    reasons = receipt["gates"][F.ARTIFACT_BUNDLE_VALIDITY]["reasons"]
    assert reasons == [{"code": "BUNDLE_FILE_UNEXPECTED", "pointer": ""}]


def test_semantically_equal_but_differently_serialised_bytes_are_not_the_canonical_file() -> None:
    def reformat(bundle: dict[str, bytes]) -> None:
        value = json.loads(bundle["analysis-run-state.json"])
        bundle["analysis-run-state.json"] = json.dumps(value).encode()

    receipt = _bundle_case(reformat)
    assert codes(receipt, F.ARTIFACT_BUNDLE_VALIDITY) == ["BUNDLE_FILE_DIFFERS_FROM_CANONICAL"]


# --- determinism and fail-closed evaluation -----------------------------------------------


def test_one_frozen_input_validates_to_byte_identical_receipts() -> None:
    fetcher = FakeFetcher({PAGE_B: PageFetchFailure(FetchFailureKind.TIMEOUT)})
    envelope = acquired(fetcher, budget=3)
    first = canonical_bytes(validate(envelope, budget=3))
    second = canonical_bytes(validate(copy.deepcopy(envelope), budget=3))
    assert first == second


def test_the_determinism_canary_sees_a_different_input() -> None:
    envelope = acquired(budget=3)
    other = tampered(envelope, lambda e: e["measurements"][0].update(run_id="run-x"))
    assert canonical_bytes(validate(envelope, budget=3)) != canonical_bytes(
        validate(other, budget=3)
    )


class RaisingContracts:
    """A contract port that raises for one contract: a defect in the validation itself."""

    def validate(self, name: str, document: Any) -> Any:
        if name == "website-evidence":
            raise RuntimeError("validator exploded")
        return CONTRACTS.validate(name, document)


def test_a_gate_that_cannot_be_evaluated_fails_closed_and_the_others_still_report() -> None:
    envelope = acquired()
    receipt = ValidateAnalysisRun(RaisingContracts(), validated_at, receipt_ids()).run(
        envelope, build_artifact_bundle(envelope), run_id=RUN_ID, declared_budget=FULL_BUDGET
    )
    emittable(receipt)
    assert codes(receipt, F.CANONICAL_VALIDITY) == ["VALIDATION_NOT_EVALUABLE"]
    assert states(receipt)[F.INPUT_CONTRACT] == "PASS"
    assert receipt["overall_state"] == "FAIL"


def test_the_registry_satisfies_the_contract_port_as_it_stands() -> None:
    """No wrapper: the runtime registry is handed to the use case directly."""
    receipt = ValidateAnalysisRun(CONTRACTS, validated_at, receipt_ids()).run(
        acquired(), build_artifact_bundle(acquired()), run_id=RUN_ID, declared_budget=FULL_BUDGET
    )
    assert receipt["gates"][F.CANONICAL_VALIDITY]["state"] == "PASS"


# --- one statement of each fact -------------------------------------------------------------


def test_the_canonical_members_are_the_ones_the_multi_page_command_line_publishes() -> None:
    assert {name: (m.contract, m.file_name) for name, m in CANONICAL_MEMBERS.items()} == (
        acquire_cli.PRODUCED_DOCUMENTS
    )
    assert {name: (list if m.plural else dict) for name, m in CANONICAL_MEMBERS.items()} == (
        acquire_cli.CONTAINER_SHAPES
    )


def test_the_canonical_serialisation_is_the_command_line_s_byte_for_byte() -> None:
    envelope = acquired()
    for name in CANONICAL_MEMBERS:
        assert canonical_bytes(envelope[name]) == acquire_cli._serialise(envelope[name]).encode()


def _with(change: Any, budget: int = FULL_BUDGET, **kwargs: Any) -> dict[str, Any]:
    return validate(tampered(acquired(budget=budget, **kwargs), change), budget=budget)


def _failed_run(failure: BootstrapFailure = BootstrapFailure.TIMEOUT) -> dict[str, Any]:
    return acquired(discovery_report=DiscoveryReport(None, bootstrap_failure=failure))


def _set_state(value: str) -> Any:
    return lambda e: e["analysis_run_state"].__setitem__("state", value)


def _bundle(change: Any) -> dict[str, Any]:
    envelope = acquired()
    bundle = build_artifact_bundle(envelope)
    change(bundle)
    return validate(envelope, bundle)


def _fetching(results: dict[str, Any], budget: int = FULL_BUDGET) -> dict[str, Any]:
    return validate(acquired(FakeFetcher(results), budget=budget), budget=budget)


def _limited(outcome: SourceOutcome) -> dict[str, Any]:
    def limit(envelope: dict[str, Any]) -> None:
        envelope["site_inventory"]["sources"][-1]["outcome"] = outcome.value

    return _with(limit)


def _conflict(envelope: dict[str, Any]) -> None:
    measurement = envelope["measurements"][0]
    measurement["assessment"] = {"collection_mode": "OBSERVED", "result_state": "CONFLICT"}
    measurement.pop("result", None)


def _credential_target() -> dict[str, Any]:
    from tests.application.test_acquire_selected_pages import REQUEST, build

    request = dict(REQUEST, target_url="https://operator:s3cr3t@example.com/")
    return validate(build(FakeFetcher(), FULL_BUDGET).run(request))


def _producer_invariant() -> dict[str, Any]:
    def unseeded(envelope: dict[str, Any]) -> None:
        seed = envelope["site_inventory"]["candidates"][0]
        seed["provenance"] = [p for p in seed["provenance"] if p != "CANONICAL_SEED"] or ["SITEMAP"]

    return _with(unseeded)


def _raising() -> dict[str, Any]:
    envelope = acquired()
    return ValidateAnalysisRun(RaisingContracts(), validated_at, receipt_ids()).run(
        envelope, build_artifact_bundle(envelope), run_id=RUN_ID, declared_budget=FULL_BUDGET
    )


#: One scenario that makes the validator give each reason code: every code is proved to be
#: *produced* by some run, not merely named somewhere. The completeness test below fails when a
#: code is added without a scenario, or when a scenario stops producing its code.
SCENARIOS: dict[ReasonCode, Any] = {
    ReasonCode.REQUEST_MISSING: lambda: validate(
        tampered(_failed_run(), lambda e: e.pop("analysis_run_request"))
    ),
    ReasonCode.REQUEST_CONTRACT_INVALID: lambda: _with(
        lambda e: e["analysis_run_request"].pop("scan_mode")
    ),
    ReasonCode.REQUEST_NOT_BOUND_TO_RUN: lambda: validate(acquired(), run_id="run-elsewhere"),
    ReasonCode.DECLARED_BUDGET_NOT_APPLIED: lambda: validate(acquired(budget=3), budget=2),
    ReasonCode.RUN_STATE_UNAVAILABLE: lambda: _with(lambda e: e.pop("analysis_run_state")),
    ReasonCode.RUN_NOT_TERMINAL: lambda: _with(_set_state("RUNNING")),
    ReasonCode.RUN_FAILED_BY_PRODUCER_DEFECT: lambda: validate(
        acquired(
            tamper=lambda e: e["sampling_manifest"]["selections"][0].__setitem__(
                "url_key", "https://example.com/nowhere"
            )
        )
    ),
    ReasonCode.RUN_FAILURE_UNCLASSIFIED: lambda: validate(
        tampered(
            _failed_run(), lambda e: e["analysis_run_state"]["failure"].__setitem__("code", "X_Y")
        )
    ),
    ReasonCode.ACQUISITION_RECORDS_MISSING: lambda: _with(lambda e: e.pop("page_acquisitions")),
    ReasonCode.CANONICAL_MEMBER_MISSING: lambda: _with(lambda e: e.pop("website_evidence")),
    ReasonCode.CANONICAL_MEMBER_UNEXPECTED: lambda: _with(
        lambda e: e.__setitem__("diagnostic_findings", [])
    ),
    ReasonCode.DOCUMENT_CONTAINER_INVALID: lambda: _with(
        lambda e: e.__setitem__("measurements", {})
    ),
    ReasonCode.DOCUMENT_CONTRACT_INVALID: lambda: _with(
        lambda e: e["measurements"][0].update(schema_version="9.9.9")
    ),
    ReasonCode.DOCUMENT_SEMANTICS_INVALID: lambda: _with(
        lambda e: e["sampling_manifest"]["selections"][1].__setitem__("selection_rank", 1)
    ),
    ReasonCode.PRODUCER_INVARIANT_BROKEN: _producer_invariant,
    ReasonCode.RUN_BINDING_BROKEN: lambda: _with(
        lambda e: e["website_evidence"][0].update(run_id="run-other")
    ),
    ReasonCode.LINKED_DOCUMENT_MISSING: lambda: _with(lambda e: e.pop("measurements")),
    ReasonCode.SELECTION_BINDING_BROKEN: lambda: _with(
        lambda e: e["sampling_manifest"].__setitem__("output_digest", "sha256:" + "0" * 64)
    ),
    ReasonCode.ACQUISITION_LINKAGE_BROKEN: lambda: _with(
        lambda e: e["website_evidence"][0].update(measurement_refs=["msr-nowhere"])
    ),
    ReasonCode.DUPLICATE_IDENTIFIER: lambda: _with(
        lambda e: e["measurements"][1].__setitem__(
            "measurement_id", e["measurements"][0]["measurement_id"]
        )
    ),
    ReasonCode.BUNDLE_FILE_MISSING: lambda: _bundle(lambda b: b.pop("site-inventory.json")),
    ReasonCode.BUNDLE_FILE_UNEXPECTED: lambda: _bundle(lambda b: b.__setitem__("x.json", b"{}")),
    ReasonCode.BUNDLE_FILE_NOT_JSON: lambda: _bundle(
        lambda b: b.__setitem__("site-inventory.json", b"{")
    ),
    ReasonCode.BUNDLE_FILE_DIFFERS_FROM_CANONICAL: lambda: _bundle(
        lambda b: b.__setitem__("analysis-run-state.json", b"{}")
    ),
    ReasonCode.VALIDATION_NOT_EVALUABLE: _raising,
    ReasonCode.RUN_FAILED_TECHNICALLY: lambda: validate(_failed_run()),
    ReasonCode.RUN_CANCELLED: lambda: _with(_set_state("CANCELLED")),
    ReasonCode.SELECTION_INCOMPLETE: lambda: validate(acquired(budget=2), budget=2),
    ReasonCode.PAGE_NOT_ACQUIRED: lambda: _fetching(
        {PAGE_B: PageFetchFailure(FetchFailureKind.DNS_FAILURE)}
    ),
    ReasonCode.PAGE_BODY_TRUNCATED: lambda: _fetching({PAGE_A: response(PAGE_A, truncated=True)}),
    ReasonCode.PAGE_BODY_NOT_DECODED: lambda: _fetching(
        {PAGE_A: response(PAGE_A, undecodable=True)}
    ),
    ReasonCode.PAGE_MEASUREMENTS_WITHHELD: lambda: _fetching(
        {PAGE_A: response(UNREPRESENTABLE)}, budget=2
    ),
    ReasonCode.PAGE_EVIDENCE_NOT_ASSESSED: lambda: _fetching(
        {PAGE_B: PageFetchFailure(FetchFailureKind.TIMEOUT)}
    ),
    ReasonCode.PAGE_EVIDENCE_UNKNOWN: lambda: _fetching(
        {PAGE_A: response(PAGE_A, content_type="")}
    ),
    ReasonCode.MEASUREMENT_WITHOUT_EVIDENCE: lambda: _with(lambda e: e["website_evidence"].pop(0)),
    ReasonCode.UNRESOLVED_CONFLICT: lambda: _with(_conflict),
    ReasonCode.DISCOVERY_SOURCE_LIMITED: lambda: _limited(SourceOutcome.PROVIDER_FAILURE),
    ReasonCode.RUN_EMITTED_NO_PAGE_DOCUMENTS: lambda: validate(_failed_run()),
    ReasonCode.REQUEST_WITHHELD_BY_POLICY: _credential_target,
}


def test_every_reason_code_has_a_scenario_that_produces_it() -> None:
    assert set(SCENARIOS) == set(ReasonCode)


@pytest.mark.parametrize("code", list(SCENARIOS), ids=[code.value for code in SCENARIOS])
def test_the_validator_actually_gives_each_reason(code: ReasonCode) -> None:
    receipt = SCENARIOS[code]()
    assert CONTRACTS.validate(RECEIPT_CONTRACT, receipt) == ()
    assert receipt_rule_violations(receipt) == ()
    assert code.value in all_codes(receipt), sorted(all_codes(receipt))


def test_the_remaining_run_state_paths_are_classified() -> None:
    def no_state(envelope: dict[str, Any]) -> None:
        envelope.pop("analysis_run_state")

    def running(envelope: dict[str, Any]) -> None:
        envelope["analysis_run_state"]["state"] = "RUNNING"

    def cancelled(envelope: dict[str, Any]) -> None:
        envelope["analysis_run_state"]["state"] = "CANCELLED"

    def no_records(envelope: dict[str, Any]) -> None:
        envelope.pop("page_acquisitions")

    expected = {
        no_state: "RUN_STATE_UNAVAILABLE",
        running: "RUN_NOT_TERMINAL",
        cancelled: "RUN_CANCELLED",
        no_records: "ACQUISITION_RECORDS_MISSING",
    }
    for change, code in expected.items():
        receipt = validate(tampered(acquired(), change))
        assert CONTRACTS.validate(RECEIPT_CONTRACT, receipt) == ()
        assert codes(receipt, F.ACQUISITION_COMPLETENESS) == [code], code


def test_a_measurement_no_evidence_names_and_a_withheld_page_are_missing_evidence() -> None:
    def orphan(envelope: dict[str, Any]) -> None:
        envelope["website_evidence"].pop(0)

    receipt = emittable(validate(tampered(acquired(), orphan)))
    assert "MEASUREMENT_WITHOUT_EVIDENCE" in codes(receipt, F.EVIDENCE_COVERAGE)

    # A redirect ending at a URL whose identity is valid but no measurement carrier can hold.
    fetcher = FakeFetcher({PAGE_A: response(UNREPRESENTABLE)})
    envelope = acquired(fetcher, budget=2)
    record = envelope["page_acquisitions"][1]
    assert record["measurements_withheld_reason"] == "SOURCE_URL_NOT_REPRESENTABLE"
    receipt = emittable(validate(envelope, budget=2))
    assert codes(receipt, F.EVIDENCE_COVERAGE) == ["PAGE_MEASUREMENTS_WITHHELD"]
    assert only_failures(receipt) == set()


# --- independent review findings (2026-09-29) ----------------------------------------------


def test_an_inventory_that_hides_a_limited_source_breaks_a_producer_invariant_and_fails() -> None:
    """A defective producer drops a cut-short source row but keeps its candidates' provenance.

    Digests are recomputed as that producer would, so no contract, digest or admission rule
    notices; only the inventory's own producer invariant does, and it must fail the run's
    validation rather than let the hidden limitation pass as a release.
    """
    from pxapi.domain.acquisition_digests import inventory_digests, manifest_digests

    limited = DiscoveryReport(
        target_origin=ORIGIN,
        observations=(
            DiscoveryObservation(ORIGIN, "CANONICAL_SEED"),
            DiscoveryObservation(PAGE_A, "SITEMAP"),
        ),
        attempts=(
            SourceAttempt("CANONICAL_SEED", SourceOutcome.USED),
            SourceAttempt("SITEMAP", SourceOutcome.TIMEOUT),
        ),
    )
    genuine = acquired(discovery_report=limited, budget=2)
    assert codes(validate(genuine, budget=2), F.UNRESOLVED_CONFLICTS_LIMITATIONS) == [
        "DISCOVERY_SOURCE_LIMITED"
    ], "canary: the genuine run states its limitation"

    def hide_the_source(envelope: dict[str, Any]) -> None:
        inventory = envelope["site_inventory"]
        inventory["sources"] = [s for s in inventory["sources"] if s["source_id"] != "SITEMAP"]
        inventory["input_digest"], inventory["output_digest"] = inventory_digests(
            inventory, [{"observed_form": ORIGIN, "source_id": "CANONICAL_SEED"}]
        )
        manifest = envelope["sampling_manifest"]
        manifest["inventory_output_digest"] = inventory["output_digest"]
        manifest["input_digest"], manifest["output_digest"] = manifest_digests(manifest)
        for record in envelope["page_acquisitions"]:
            record["sampling_manifest_output_digest"] = manifest["output_digest"]

    receipt = emittable(validate(tampered(genuine, hide_the_source), budget=2))
    reasons = receipt["gates"][F.CANONICAL_VALIDITY]["reasons"]
    assert {
        "code": "PRODUCER_INVARIANT_BROKEN",
        "pointer": "/site_inventory/candidates",
        "rule": "source_declared_for_every_provenance",
    } in reasons
    assert receipt["overall_state"] == "FAIL"


def test_a_credential_bearing_target_refused_by_policy_is_blocked_never_failed() -> None:
    """The producer withholds the request on purpose (data minimisation); that is no defect."""
    from tests.application.test_acquire_selected_pages import REQUEST, build

    request = dict(REQUEST, target_url="https://operator:s3cr3t@example.com/")
    envelope = build(FakeFetcher(), FULL_BUDGET).run(request)
    assert "analysis_run_request" not in envelope, "canary: the producer withheld the request"
    assert envelope["analysis_run_state"]["failure"] == {"code": TARGET_NOT_PERMITTED_CODE}
    receipt = emittable(validate(envelope))
    assert receipt["overall_state"] == "BLOCKED"
    assert only_failures(receipt) == set()
    assert receipt["gates"][F.INPUT_CONTRACT]["state"] == "NOT_APPLICABLE"
    assert codes(receipt, F.INPUT_CONTRACT) == ["REQUEST_WITHHELD_BY_POLICY"]
    assert "s3cr3t" not in json.dumps(receipt)


def test_a_request_missing_for_any_other_reason_is_still_a_defect() -> None:
    def drop(envelope: dict[str, Any]) -> None:
        envelope.pop("analysis_run_request")

    unreachable = DiscoveryReport(None, bootstrap_failure=BootstrapFailure.UNREACHABLE)
    receipt = emittable(validate(tampered(acquired(discovery_report=unreachable), drop)))
    assert codes(receipt, F.INPUT_CONTRACT) == ["REQUEST_MISSING"]
    assert receipt["overall_state"] == "FAIL"


@pytest.mark.parametrize("outcome", sorted(LIMITING_SOURCE_OUTCOMES))
def test_every_limiting_source_outcome_is_a_stated_limitation(outcome: str) -> None:
    def limit(envelope: dict[str, Any]) -> None:
        envelope["site_inventory"]["sources"][-1]["outcome"] = outcome

    receipt = validate(tampered(acquired(), limit))
    assert "DISCOVERY_SOURCE_LIMITED" in codes(receipt, F.UNRESOLVED_CONFLICTS_LIMITATIONS)
