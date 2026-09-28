"""What ``analysis-validation-receipt.v1`` states beyond the generic registry rules.

The generic suites already cover it as they cover every contract — examples valid, invalid
fixtures failing for their reason, closed objects, pinned version, pinned closed vocabularies.
This module adds what only this contract has: the gate families are *member names* rather than
an ``enum``, so the closed-vocabulary scan cannot see them and they are pinned here instead; and
every registered example must also satisfy the Domain's receipt rules, because an example that
JSON Schema accepts but the rules refuse would teach a consumer a receipt no producer may emit.
"""

from __future__ import annotations

from typing import Any

import pytest

from pxapi.domain.run_validation import (
    ANALYSIS_VALIDATION_RECEIPT,
    GateFamily,
    receipt_rule_violations,
)
from tests.contracts.support import CONTRACTS, load_json

SCHEMA: dict[str, Any] = load_json(CONTRACTS.schema_path(ANALYSIS_VALIDATION_RECEIPT))
EXAMPLES = CONTRACTS.example_paths(ANALYSIS_VALIDATION_RECEIPT)
FAMILIES = [family.value for family in GateFamily]


def test_the_contract_is_registered_under_the_domain_s_name_and_owner_slice() -> None:
    entry = CONTRACTS.entry(ANALYSIS_VALIDATION_RECEIPT)
    assert entry["owner_slice"] == "PXAPI-25"
    assert entry["version"] == "1.0.0"


def test_the_gates_are_exactly_the_seven_families_in_the_declared_order() -> None:
    gates = SCHEMA["properties"]["gates"]
    assert list(gates["properties"]) == FAMILIES
    assert gates["required"] == FAMILIES
    assert gates["additionalProperties"] is False


def test_every_gate_family_is_the_same_gate_shape() -> None:
    gates = SCHEMA["properties"]["gates"]["properties"]
    assert {member["$ref"] for member in gates.values()} == {"#/$defs/gate"}


def test_the_receipt_carries_no_score_severity_polarity_or_release_member() -> None:
    forbidden = {"score", "severity", "polarity", "customer_release", "finding", "grade"}
    assert not forbidden & set(SCHEMA["properties"])
    assert SCHEMA["additionalProperties"] is False


@pytest.mark.parametrize("path", EXAMPLES, ids=[path.name for path in EXAMPLES])
def test_every_example_also_satisfies_the_receipt_rules(path: Any) -> None:
    assert receipt_rule_violations(load_json(path)) == ()


def test_the_examples_illustrate_every_overall_state_and_a_neutral_gate() -> None:
    documents = [load_json(path) for path in EXAMPLES]
    assert {document["overall_state"] for document in documents} == {"PASS", "FAIL", "BLOCKED"}
    gate_states = {gate["state"] for document in documents for gate in document["gates"].values()}
    assert gate_states == {"PASS", "FAIL", "BLOCKED", "NOT_APPLICABLE"}


def test_a_succeeded_run_is_illustrated_as_blocked_and_as_failed() -> None:
    """SUCCEEDED is not PASS: the registry itself shows a succeeded run that does not pass."""
    outcomes = {
        load_json(path)["overall_state"]
        for path in EXAMPLES
        if load_json(path).get("run_state") == "SUCCEEDED"
    }
    assert {"BLOCKED", "FAIL"} <= outcomes


def test_the_receipt_rules_see_a_planted_defect_in_a_registered_example() -> None:
    """Canary: the rule check above would pass vacuously if it never reported anything."""
    document = load_json(EXAMPLES[0])
    document["overall_state"] = "PASS"
    assert receipt_rule_violations(document)
