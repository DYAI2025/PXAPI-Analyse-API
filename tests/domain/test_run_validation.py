"""The run-validation vocabulary and its two decisions: a gate's state, and the run's state.

The precedence is decided exhaustively, over every assignment of the four gate states to the
seven gate families, rather than by examples; every receipt rule is proved to fire on a
counterexample and to stay silent on a receipt that keeps it.
"""

from __future__ import annotations

import copy
import itertools
import random
from typing import Any

import pytest

from pxapi.domain.run_state import RunState
from pxapi.domain.run_validation import (
    OVERALL_STATES,
    REASONS,
    RECEIPT_RULES,
    GateFamily,
    GateState,
    ReasonCode,
    gate_document,
    gate_state_of,
    ordered_reasons,
    overall_state_of,
    reason,
    reason_codes_with_effect,
    receipt_rule_violations,
)

# --- the vocabulary ---------------------------------------------------------------------------


def test_the_seven_gate_families_are_exactly_those_of_validation_v1_in_order() -> None:
    assert [family.value for family in GateFamily] == [
        "INPUT_CONTRACT",
        "ACQUISITION_COMPLETENESS",
        "CANONICAL_VALIDITY",
        "PROVENANCE_LINKAGE",
        "EVIDENCE_COVERAGE",
        "UNRESOLVED_CONFLICTS_LIMITATIONS",
        "ARTIFACT_BUNDLE_VALIDITY",
    ]


def test_the_gate_states_are_exactly_the_four() -> None:
    assert [state.value for state in GateState] == ["PASS", "FAIL", "BLOCKED", "NOT_APPLICABLE"]


def test_every_reason_code_is_specified_once_with_an_effect_that_is_not_pass() -> None:
    assert set(REASONS) == set(ReasonCode)
    for code, spec in REASONS.items():
        assert spec.effect is not GateState.PASS, code
        assert spec.families, f"{code}: no gate family may give it"
        assert spec.meaning.strip(), code


def test_every_gate_family_has_a_reason_of_its_own() -> None:
    """A gate whose only reason were the shared "not evaluable" could detect nothing."""
    for family in GateFamily:
        own = [
            code
            for code, spec in REASONS.items()
            if family in spec.families and code is not ReasonCode.VALIDATION_NOT_EVALUABLE
        ]
        assert own, f"{family}: no reason of its own"


def test_the_evidence_gates_can_block_but_fail_only_when_they_cannot_be_evaluated() -> None:
    """Missing or conflicting evidence is a limitation, never a defect: the two evidence gates
    own no FAIL reason, so they fail only when the documents in hand could not be read."""
    for family in (GateFamily.EVIDENCE_COVERAGE, GateFamily.UNRESOLVED_CONFLICTS_LIMITATIONS):
        fails = {
            code
            for code, spec in REASONS.items()
            if family in spec.families and spec.effect is GateState.FAIL
        }
        assert fails == {ReasonCode.VALIDATION_NOT_EVALUABLE}, family


def test_a_gate_that_cannot_be_evaluated_may_say_so_in_every_family() -> None:
    assert REASONS[ReasonCode.VALIDATION_NOT_EVALUABLE].families == frozenset(GateFamily)
    assert REASONS[ReasonCode.VALIDATION_NOT_EVALUABLE].effect is GateState.FAIL


@pytest.mark.parametrize(
    "code",
    [
        ReasonCode.SELECTION_INCOMPLETE,
        ReasonCode.PAGE_NOT_ACQUIRED,
        ReasonCode.RUN_FAILED_TECHNICALLY,
        ReasonCode.PAGE_EVIDENCE_NOT_ASSESSED,
        ReasonCode.PAGE_EVIDENCE_UNKNOWN,
        ReasonCode.PAGE_MEASUREMENTS_WITHHELD,
        ReasonCode.PAGE_BODY_TRUNCATED,
        ReasonCode.PAGE_BODY_NOT_DECODED,
        ReasonCode.DISCOVERY_SOURCE_LIMITED,
    ],
)
def test_technical_limitations_block_and_never_fail(code: ReasonCode) -> None:
    """Neutrality: an incomplete selection, a timeout, a refusal or an assessment that was not
    made is a limitation of our process, and a limitation is never a defect."""
    assert REASONS[code].effect is GateState.BLOCKED


def test_the_reason_codes_of_one_effect_are_listed_in_declaration_order() -> None:
    blocked = reason_codes_with_effect(GateState.BLOCKED)
    declared = [code.value for code in ReasonCode]
    assert blocked == [code for code in declared if code in blocked]
    assert reason_codes_with_effect(GateState.PASS) == []


# --- a gate's state -------------------------------------------------------------------------


def test_a_gate_with_no_reason_passes() -> None:
    assert gate_state_of([]) is GateState.PASS


@pytest.mark.parametrize("code", list(ReasonCode), ids=[code.value for code in ReasonCode])
def test_a_gate_with_one_reason_takes_that_reason_s_effect(code: ReasonCode) -> None:
    assert gate_state_of([code.value]) is REASONS[code].effect


def test_a_defect_outranks_a_limitation_inside_one_gate() -> None:
    codes = [ReasonCode.PAGE_NOT_ACQUIRED.value, ReasonCode.RUN_FAILURE_UNCLASSIFIED.value]
    assert gate_state_of(codes) is GateState.FAIL
    assert gate_state_of(reversed(codes)) is GateState.FAIL


def test_an_unknown_reason_code_is_refused_rather_than_read_as_no_reason() -> None:
    with pytest.raises(ValueError):
        gate_state_of(["WEBSITE_LOOKS_BAD"])


# --- the run's state: exhaustive precedence -------------------------------------------------

ALL_ASSIGNMENTS = list(itertools.product(list(GateState), repeat=len(GateFamily)))


def test_the_assignment_space_is_every_combination() -> None:
    """Canary: the exhaustive check below covers 4^7 assignments, not a sample."""
    assert len(ALL_ASSIGNMENTS) == 4 ** len(GateFamily) == 16384


def test_the_precedence_is_fail_then_blocked_then_pass_with_not_applicable_neutral() -> None:
    for assignment in ALL_ASSIGNMENTS:
        seen = set(assignment)
        if GateState.FAIL in seen:
            expected = GateState.FAIL
        elif GateState.BLOCKED in seen:
            expected = GateState.BLOCKED
        elif GateState.PASS in seen:
            expected = GateState.PASS
        else:
            expected = GateState.BLOCKED
        assert overall_state_of(assignment) is expected, assignment


def test_not_applicable_never_changes_the_overall_state() -> None:
    """Replacing any gate by NOT_APPLICABLE never moves the result, unless nothing is left."""
    for assignment in ALL_ASSIGNMENTS:
        applicable = [state for state in assignment if state is not GateState.NOT_APPLICABLE]
        if applicable:
            assert overall_state_of(assignment) is overall_state_of(applicable)


def test_nothing_applicable_establishes_nothing_and_is_blocked_rather_than_pass() -> None:
    assert overall_state_of([GateState.NOT_APPLICABLE] * 7) is GateState.BLOCKED
    assert overall_state_of([]) is GateState.BLOCKED


def test_the_overall_states_exclude_the_neutral_one() -> None:
    assert GateState.NOT_APPLICABLE not in OVERALL_STATES
    produced = {overall_state_of(assignment) for assignment in ALL_ASSIGNMENTS}
    assert produced == set(OVERALL_STATES)


# --- reason ordering --------------------------------------------------------------------------


def test_reasons_are_ordered_by_code_pointer_rule_whatever_order_they_were_found_in() -> None:
    found = [
        reason(ReasonCode.PAGE_NOT_ACQUIRED, "/page_acquisitions/2"),
        reason(ReasonCode.DOCUMENT_CONTRACT_INVALID, "/measurements/1", "const"),
        reason(ReasonCode.PAGE_NOT_ACQUIRED, "/page_acquisitions/10"),
        reason(ReasonCode.DOCUMENT_CONTRACT_INVALID, "/measurements/1", "additionalProperties"),
        reason(ReasonCode.SELECTION_INCOMPLETE),
    ]
    expected = ordered_reasons(found)
    shuffler = random.Random(25)
    for _ in range(50):
        permutation = found[:]
        shuffler.shuffle(permutation)
        assert ordered_reasons(permutation) == expected
    assert [(r["code"], r.get("pointer"), r.get("rule")) for r in expected] == [
        ("DOCUMENT_CONTRACT_INVALID", "/measurements/1", "additionalProperties"),
        ("DOCUMENT_CONTRACT_INVALID", "/measurements/1", "const"),
        ("PAGE_NOT_ACQUIRED", "/page_acquisitions/10", None),
        ("PAGE_NOT_ACQUIRED", "/page_acquisitions/2", None),
        ("SELECTION_INCOMPLETE", None, None),
    ]


def test_a_repeated_reason_is_reported_once() -> None:
    twice = [reason(ReasonCode.SELECTION_INCOMPLETE, "/x")] * 2
    assert ordered_reasons(twice) == [{"code": "SELECTION_INCOMPLETE", "pointer": "/x"}]


def test_a_gate_document_derives_its_state_from_its_reasons() -> None:
    assert gate_document([]) == {"state": "PASS", "reasons": []}
    assert gate_document([reason(ReasonCode.RUN_EMITTED_NO_PAGE_DOCUMENTS)])["state"] == (
        "NOT_APPLICABLE"
    )


# --- the receipt rules ----------------------------------------------------------------------


def receipt_with(**gate_reasons: list[dict[str, str]]) -> dict[str, Any]:
    """A receipt built from the rules themselves, with the given reasons per gate family."""
    gates = {
        family.value: gate_document(gate_reasons.get(family.value, [])) for family in GateFamily
    }
    return {
        "run_state": RunState.SUCCEEDED.value,
        "overall_state": overall_state_of(GateState(g["state"]) for g in gates.values()).value,
        "gates": gates,
    }


def test_a_receipt_built_by_the_rules_breaks_none_of_them() -> None:
    """Canary: without this, every counterexample below could pass by always reporting."""
    assert receipt_rule_violations(receipt_with()) == ()
    blocked = receipt_with(EVIDENCE_COVERAGE=[reason(ReasonCode.PAGE_EVIDENCE_UNKNOWN, "/p/0")])
    assert receipt_rule_violations(blocked) == ()


def _rules(receipt: Any) -> set[str]:
    return {violation.rule for violation in receipt_rule_violations(receipt)}


def _drop_gate(receipt: dict[str, Any]) -> None:
    receipt["gates"].pop("EVIDENCE_COVERAGE")


def _borrowed_reason(receipt: dict[str, Any]) -> None:
    receipt["gates"]["INPUT_CONTRACT"] = gate_document(
        [reason(ReasonCode.BUNDLE_FILE_MISSING, "/x.json")]
    )
    receipt["overall_state"] = "FAIL"


def _hand_set_state(receipt: dict[str, Any]) -> None:
    receipt["gates"]["CANONICAL_VALIDITY"]["state"] = "BLOCKED"
    receipt["overall_state"] = "BLOCKED"


def _unordered(receipt: dict[str, Any]) -> None:
    receipt["gates"]["ACQUISITION_COMPLETENESS"] = {
        "state": "BLOCKED",
        "reasons": [
            reason(ReasonCode.SELECTION_INCOMPLETE),
            reason(ReasonCode.PAGE_NOT_ACQUIRED, "/page_acquisitions/1"),
        ],
    }
    receipt["overall_state"] = "BLOCKED"


def _overall_misstated(receipt: dict[str, Any]) -> None:
    receipt["gates"]["EVIDENCE_COVERAGE"] = gate_document(
        [reason(ReasonCode.PAGE_EVIDENCE_NOT_ASSESSED, "/page_acquisitions/0")]
    )


def _pass_for_failed_run(receipt: dict[str, Any]) -> None:
    receipt["run_state"] = RunState.FAILED.value


RULE_COUNTEREXAMPLES = {
    "every_gate_present": _drop_gate,
    "reason_belongs_to_gate": _borrowed_reason,
    "gate_state_follows_reasons": _hand_set_state,
    "reasons_ordered_and_unique": _unordered,
    "overall_state_follows_gates": _overall_misstated,
    "pass_requires_succeeded_run": _pass_for_failed_run,
}


@pytest.mark.parametrize("rule", sorted(RULE_COUNTEREXAMPLES))
def test_each_receipt_rule_fires_on_its_counterexample(rule: str) -> None:
    receipt = receipt_with()
    RULE_COUNTEREXAMPLES[rule](receipt)
    assert rule in _rules(receipt)


def test_every_receipt_rule_has_a_counterexample() -> None:
    assert set(RULE_COUNTEREXAMPLES) == set(RECEIPT_RULES)


@pytest.mark.parametrize(
    "malformed",
    [None, [], "PASS", {"gates": []}, {"gates": {"INPUT_CONTRACT": 3}}, {"gates": {"X": {}}}],
    ids=["none", "list", "string", "gates-list", "gate-int", "gate-unknown"],
)
def test_a_malformed_receipt_is_reported_and_never_raises(malformed: Any) -> None:
    assert receipt_rule_violations(copy.deepcopy(malformed)), "nothing reported"


def test_an_unhashable_reason_code_is_a_violation_rather_than_a_crash() -> None:
    receipt = receipt_with()
    receipt["gates"]["INPUT_CONTRACT"] = {"state": "PASS", "reasons": [{"code": ["X"]}]}
    assert "reason_belongs_to_gate" in _rules(receipt)
