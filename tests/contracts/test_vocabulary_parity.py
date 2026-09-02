"""The contract vocabularies and the domain vocabularies are one vocabulary.

A run state, a stage or a status that exists in ``common.v1.json`` but not in the domain (or
the other way round) would let a document describe a run the code cannot reach. These tests
compare the enum lists to the enums, in order, and the failure-stage rule of the run-state
contract to ``FAILURE_STATE_FOR``.
"""

from __future__ import annotations

from typing import Any

from pxapi.domain.run_state import FAILURE_STATES, IllegalTransition, RunState
from pxapi.domain.stage_execution import FAILURE_STATE_FOR, Stage, StageStatus
from tests.contracts.support import (
    CANONICAL_CONTRACT_NAMES,
    SUPPORT_CONTRACT_NAMES,
    load_json,
    manifest,
    schema_path,
)


def _common_enum(name: str) -> list[str]:
    return load_json(schema_path("common"))["$defs"][name]["enum"]


def test_run_state_enum_matches_the_domain_in_order() -> None:
    assert _common_enum("run_state") == [state.value for state in RunState]


def test_stage_enum_matches_the_domain_in_order() -> None:
    assert _common_enum("stage") == [stage.value for stage in Stage]


def test_stage_status_enum_matches_the_domain_in_order() -> None:
    assert _common_enum("stage_status") == [status.value for status in StageStatus]


def test_contract_name_enum_matches_the_manifest() -> None:
    assert _common_enum("contract_name") == [*CANONICAL_CONTRACT_NAMES, *SUPPORT_CONTRACT_NAMES]
    listed = [entry["name"] for entry in (*manifest()["canonical"], *manifest()["support"])]
    assert _common_enum("contract_name") == listed


def _failure_stage_rule() -> dict[str, list[str] | None]:
    """``state -> allowed failure_stage values`` as the run-state contract encodes it."""
    schema = load_json(schema_path("analysis-run-state"))
    rule: dict[str, list[str] | None] = {}
    for clause in schema["allOf"]:
        condition = clause["if"]["properties"]["state"]
        if "const" not in condition:
            continue
        state = condition["const"]
        constraint: dict[str, Any] = clause["then"]["properties"]["failure"]["properties"][
            "failure_stage"
        ]
        rule[state] = None if constraint.get("type") == "null" else constraint["enum"]
    return rule


def test_run_state_contract_failure_stage_rule_equals_failure_state_for() -> None:
    rule = _failure_stage_rule()
    assert set(rule) == {state.value for state in FAILURE_STATES}, "one clause per failure state"
    assert rule[RunState.BLOCKED_INPUT.value] is None, "BLOCKED_INPUT has no stage"
    for state in FAILURE_STATES - {RunState.BLOCKED_INPUT}:
        expected = [stage.value for stage in Stage if FAILURE_STATE_FOR[stage] is state]
        assert rule[state.value] == expected, state.value
    covered = [stage for stages in rule.values() if stages for stage in stages]
    assert sorted(covered) == sorted(stage.value for stage in Stage), "every stage exactly once"


def test_failure_state_list_in_the_contract_is_the_domain_failure_set() -> None:
    schema = load_json(schema_path("analysis-run-state"))
    first = schema["allOf"][0]["if"]["properties"]["state"]["enum"]
    assert set(first) == {state.value for state in FAILURE_STATES}


def test_illegal_transition_code_is_a_registered_problem_code() -> None:
    codes = {item["code"] for item in manifest()["problem_codes"]}
    assert IllegalTransition.code in codes
