"""A technical failure can never become a finding about the website.

This slice adds the smallest vocabulary that keeps six situations structurally distinct: a
measurement that ran and has a value, one that ran and has none, one whose observations
conflict, one that does not apply to the subject, and one that never happened at all — with a
reason that names the analysis process, never the site. The sixth is the point of the exercise:
a provider failure, a runtime error or a timeout must be *incapable* of carrying a website
judgement, rather than merely discouraged from carrying one.

The proofs below are exhaustive over the declared vocabularies rather than illustrative. Every
assessment the contracts admit is built from the pinned enums in ``tests.test_closed_vocabularies``
and run through both carriers, so widening a vocabulary widens this matrix too and a token
nobody thought about cannot slip past on the strength of the cases someone happened to write.

The three vocabularies are stated once, in the pin module, and imported here. Where a rule is
already owned by a generic registry test — closure, version pinning, example validity — it is
not restated; this module holds what is specific to assessment semantics.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.contracts.support import CONTRACTS, load_json
from tests.test_closed_vocabularies import (
    COLLECTION_MODES,
    NOT_ASSESSED_REASONS,
    POLARITIES,
    RESULT_STATES,
    VALUE_TYPES,
)

MEASUREMENT = "measurement-record"
EVIDENCE = "website-evidence"

#: The shared definition file holding the assessment block. It is deliberately not a registered
#: contract: it is embedded in both carriers, and a registered contract must pin its own
#: ``schema_version`` at its root, which would drag a nested version into every embedding
#: document.
ASSESSMENT_SHARED = "assessment"

#: The one result state that carries a website value. Everything else is an outcome *about the
#: assessment*, never about the site.
KNOWN = "KNOWN"

#: Every assessment that was actually performed: how it was collected, and what came of it.
PERFORMED: list[dict[str, str]] = [
    {"collection_mode": mode, "result_state": state}
    for mode in COLLECTION_MODES
    for state in RESULT_STATES
]

#: Every assessment that never happened, one per registered reason.
NOT_ASSESSED: list[dict[str, str]] = [
    {"not_assessed_reason": reason} for reason in NOT_ASSESSED_REASONS
]

PERFORMED_KNOWN = [a for a in PERFORMED if a["result_state"] == KNOWN]

#: Performed but valueless, plus never assessed: every assessment that must not be able to
#: express a website value or a website polarity.
WITHOUT_VALUE = [a for a in PERFORMED if a["result_state"] != KNOWN] + NOT_ASSESSED

RUN_ID = "run-01JQ8Z4K2M0000000000000001"
MEASUREMENT_ID = "msr-01JQ8Z4K2M0000000000000001"
EVIDENCE_ID = "evd-01JQ8Z4K2M0000000000000001"
SOURCE_URL = "https://example.com/"


def _id(assessment: dict[str, str]) -> str:
    return "+".join(assessment.values()) or "empty"


def measurement(assessment: dict[str, str], **overrides: Any) -> dict[str, Any]:
    """A measurement record carrying ``assessment``, with a result exactly when it is KNOWN."""
    document: dict[str, Any] = {
        "schema_version": CONTRACTS.entry(MEASUREMENT)["version"],
        "run_id": RUN_ID,
        "measurement_id": MEASUREMENT_ID,
        "metric_id": "HTTP_STATUS",
        "source_url": SOURCE_URL,
        "observed_at": "2026-09-06T09:12:47Z",
        "collector": "HTTP_BASELINE",
        "collector_version": "1.0.0",
        "assessment": dict(assessment),
    }
    if assessment.get("result_state") == KNOWN:
        document["result"] = {"value_type": "INTEGER", "integer_value": 200}
    document.update(overrides)
    return document


def evidence(assessment: dict[str, str], **overrides: Any) -> dict[str, Any]:
    """Website evidence carrying ``assessment``, referencing a measurement exactly when KNOWN."""
    known = assessment.get("result_state") == KNOWN
    document: dict[str, Any] = {
        "schema_version": CONTRACTS.entry(EVIDENCE)["version"],
        "run_id": RUN_ID,
        "evidence_id": EVIDENCE_ID,
        "source_url": SOURCE_URL,
        "observed_at": "2026-09-06T09:12:51Z",
        "scenario": "HOMEPAGE_FETCH",
        "collector": "HTTP_BASELINE",
        "collector_version": "1.0.0",
        "assessment": dict(assessment),
        "measurement_refs": [MEASUREMENT_ID] if known else [],
    }
    document.update(overrides)
    return document


CARRIERS = ((MEASUREMENT, measurement), (EVIDENCE, evidence))
CARRIER_IDS = [name for name, _ in CARRIERS]


def _keys(contract: str, document: dict[str, Any]) -> set[tuple[str, str]]:
    return {violation.key for violation in CONTRACTS.validate(contract, document)}


# --- canaries against a vacuous matrix ----------------------------------------------------


def test_the_assessment_matrix_is_not_empty() -> None:
    """Without this, every parametrised proof below would pass over an empty list."""
    assert len(PERFORMED) == len(COLLECTION_MODES) * len(RESULT_STATES) > 0
    assert len(NOT_ASSESSED) == len(NOT_ASSESSED_REASONS) > 0
    assert PERFORMED_KNOWN and WITHOUT_VALUE and POLARITIES


def test_the_two_carriers_are_registered_and_the_assessment_block_is_shared() -> None:
    """The block is embedded twice, so it is a shared definition rather than a contract."""
    assert CONTRACTS.has_contract(MEASUREMENT) and CONTRACTS.has_contract(EVIDENCE)
    assert ASSESSMENT_SHARED in {s["name"] for s in CONTRACTS.shared_definitions()}
    assert not CONTRACTS.has_contract(ASSESSMENT_SHARED), (
        "a registered contract must pin its own schema_version at its root, which an embedded "
        "block would drag into every document that carries it"
    )


# --- what is legal ------------------------------------------------------------------------


@pytest.mark.parametrize("assessment", PERFORMED + NOT_ASSESSED, ids=_id)
def test_every_declared_assessment_validates_on_both_carriers(assessment: dict[str, str]) -> None:
    for contract, build in CARRIERS:
        found = CONTRACTS.validate(contract, build(assessment))
        assert found == (), f"{contract}/{_id(assessment)}: {sorted(v.key for v in found)}"


@pytest.mark.parametrize("polarity", POLARITIES)
def test_a_known_observation_may_carry_either_polarity(polarity: str) -> None:
    for assessment in PERFORMED_KNOWN:
        assert CONTRACTS.validate(EVIDENCE, evidence(assessment, polarity=polarity)) == ()


@pytest.mark.parametrize("assessment", PERFORMED_KNOWN, ids=_id)
def test_a_known_observation_may_also_state_no_judgement_at_all(
    assessment: dict[str, str],
) -> None:
    """A factual observation omits polarity rather than being forced to invent one.

    This is why there is no NEUTRAL token: "known, and neither good nor bad" is the absence of
    a judgement, and a vocabulary entry for it would invite a reader to treat it as one.
    """
    document = evidence(assessment)
    assert "polarity" not in document
    assert CONTRACTS.validate(EVIDENCE, document) == ()


# --- what a failure may never become ------------------------------------------------------

POLARITY_CASES = [(a, p) for a in WITHOUT_VALUE for p in POLARITIES]
POLARITY_IDS = [f"{_id(a)}+{p}" for a, p in POLARITY_CASES]


@pytest.mark.parametrize(("assessment", "polarity"), POLARITY_CASES, ids=POLARITY_IDS)
def test_no_assessment_without_a_known_result_may_carry_a_website_polarity(
    assessment: dict[str, str], polarity: str
) -> None:
    """The rule this slice exists for, over every valueless assessment and both polarities.

    POSITIVE is refused as firmly as NEGATIVE: the ban is on stating a judgement about a site
    nobody established anything about, not merely on stating an unflattering one.
    """
    assert ("", "not") in _keys(EVIDENCE, evidence(assessment, polarity=polarity))


@pytest.mark.parametrize("assessment", WITHOUT_VALUE, ids=_id)
def test_no_assessment_without_a_known_result_may_carry_a_measured_value(
    assessment: dict[str, str],
) -> None:
    """A missing measurement cannot arrive downstream as a zero, which is how it usually does."""
    zero = {"value_type": "INTEGER", "integer_value": 0}
    assert ("", "not") in _keys(MEASUREMENT, measurement(assessment, result=zero))


BOTH_GROUPS = [(m, r) for m in COLLECTION_MODES for r in NOT_ASSESSED_REASONS]


@pytest.mark.parametrize(("mode", "reason"), BOTH_GROUPS, ids=[f"{m}+{r}" for m, r in BOTH_GROUPS])
@pytest.mark.parametrize(("contract", "build"), CARRIERS, ids=CARRIER_IDS)
def test_a_document_cannot_be_both_performed_and_never_assessed(
    contract: str, build: Any, mode: str, reason: str
) -> None:
    """No consumer should ever have to decide which half of a contradictory document to trust."""
    assessment = {"collection_mode": mode, "result_state": KNOWN, "not_assessed_reason": reason}
    assert ("/assessment", "not") in _keys(contract, build(assessment))


@pytest.mark.parametrize("mode", COLLECTION_MODES)
@pytest.mark.parametrize(("contract", "build"), CARRIERS, ids=CARRIER_IDS)
def test_a_performed_assessment_without_a_result_state_is_incomplete(
    contract: str, build: Any, mode: str
) -> None:
    """An activity with no stated outcome is a gap a reader could only close by guessing."""
    assert ("/assessment", "required") in _keys(contract, build({"collection_mode": mode}))


@pytest.mark.parametrize("state", RESULT_STATES)
@pytest.mark.parametrize(("contract", "build"), CARRIERS, ids=CARRIER_IDS)
def test_a_result_state_without_a_collection_mode_is_incomplete(
    contract: str, build: Any, state: str
) -> None:
    """How something was collected is part of what the result means, not decoration."""
    assert ("/assessment", "required") in _keys(contract, build({"result_state": state}))


@pytest.mark.parametrize(("contract", "build"), CARRIERS, ids=CARRIER_IDS)
def test_an_empty_assessment_states_nothing_and_is_refused(contract: str, build: Any) -> None:
    assert ("/assessment", "required") in _keys(contract, build({}))


@pytest.mark.parametrize("assessment", PERFORMED_KNOWN, ids=_id)
def test_known_website_evidence_must_name_a_measurement_it_came_from(
    assessment: dict[str, str],
) -> None:
    """Derived evidence with nothing measured behind it is an assertion, not evidence."""
    document = evidence(assessment, measurement_refs=[])
    assert ("/measurement_refs", "minItems") in _keys(EVIDENCE, document)


@pytest.mark.parametrize("assessment", PERFORMED_KNOWN, ids=_id)
def test_a_known_measurement_without_a_result_is_refused(assessment: dict[str, str]) -> None:
    document = measurement(assessment)
    del document["result"]
    assert ("", "required") in _keys(MEASUREMENT, document)


# --- the bounded value representation -----------------------------------------------------

#: One representative value per declared type. The next test proves this covers the whole
#: closed vocabulary, so a fifth type cannot be added without a case for it.
VALUE_CASES = [
    ("BOOLEAN", "boolean_value", True),
    ("INTEGER", "integer_value", 200),
    ("TEXT", "text_value", "text/html; charset=utf-8"),
    ("URL", "url_value", "https://example.com/en/"),
]
VALUE_IDS = [case[0] for case in VALUE_CASES]


def test_the_value_type_cases_cover_the_whole_declared_vocabulary() -> None:
    assert VALUE_IDS == VALUE_TYPES


def test_the_measured_value_is_a_closed_discriminated_shape_and_not_an_open_node() -> None:
    """No ``value: any``. Every member admits exactly one JSON type, chosen by ``value_type``."""
    result = load_json(CONTRACTS.schema_path(MEASUREMENT))["properties"]["result"]
    assert result["additionalProperties"] is False
    assert result["required"] == ["value_type"]
    assert set(result["properties"]) - {"value_type"} == {member for _, member, _ in VALUE_CASES}
    for member, declared in result["properties"].items():
        assert not isinstance(declared.get("type"), list), (
            f"result.{member} admits several JSON types, which is the open node this "
            "representation exists to avoid"
        )


@pytest.mark.parametrize(("value_type", "member", "value"), VALUE_CASES, ids=VALUE_IDS)
def test_each_value_type_carries_its_own_member_and_refuses_the_others(
    value_type: str, member: str, value: Any
) -> None:
    assessment = PERFORMED_KNOWN[0]
    result = {"value_type": value_type, member: value}
    assert CONTRACTS.validate(MEASUREMENT, measurement(assessment, result=result)) == ()
    for _, other_member, other_value in VALUE_CASES:
        if other_member == member:
            continue
        mismatched = {"value_type": value_type, other_member: other_value}
        assert CONTRACTS.validate(MEASUREMENT, measurement(assessment, result=mismatched)), (
            f"{value_type} accepted {other_member}"
        )


def test_an_untyped_value_member_cannot_be_smuggled_into_the_result() -> None:
    result = {"value_type": "INTEGER", "integer_value": 200, "value": {"anything": True}}
    document = measurement(PERFORMED_KNOWN[0], result=result)
    assert ("/result", "additionalProperties") in _keys(MEASUREMENT, document)


# --- the raw-data boundary ----------------------------------------------------------------

#: Member names that would carry a provider's raw payload inline. The ban is enforced on the
#: two contracts this slice owns, not registry-wide: what a later, separately authorised
#: contract may hold is not PXK-61's decision.
RAW_PAYLOAD_MEMBERS = (
    "raw_html",
    "raw_body",
    "raw_response",
    "response_body",
    "body",
    "html",
    "payload",
    "screenshot",
    "headers",
)

SLICE_CONTRACTS = (MEASUREMENT, EVIDENCE)


def _raw_members(members: Any) -> list[str]:
    return sorted({m for m in members for fragment in RAW_PAYLOAD_MEMBERS if fragment in m})


def test_the_raw_member_scan_sees_a_planted_payload_member() -> None:
    """Canary: the scan below must detect an inline payload if one were added."""
    assert _raw_members({"measurement_id", "raw_html", "response_body"}) == [
        "raw_html",
        "response_body",
    ]
    assert _raw_members({"measurement_id", "raw_artifact_ref"}) == []


@pytest.mark.parametrize("contract", SLICE_CONTRACTS)
def test_this_slices_contracts_declare_no_inline_raw_payload_member(contract: str) -> None:
    declared = load_json(CONTRACTS.schema_path(contract))["properties"]
    assert _raw_members(declared) == [], f"{contract} carries raw data inline"


RAW_CASES = [(c, m) for c in SLICE_CONTRACTS for m in RAW_PAYLOAD_MEMBERS]


@pytest.mark.parametrize(("contract", "member"), RAW_CASES, ids=[f"{c}/{m}" for c, m in RAW_CASES])
def test_an_inline_raw_payload_is_refused_by_the_closed_root(contract: str, member: str) -> None:
    build = dict(CARRIERS)[contract]
    document = build(PERFORMED_KNOWN[0], **{member: "<!doctype html><html></html>"})
    assert ("", "additionalProperties") in _keys(contract, document)


def test_the_artifact_reference_is_an_opaque_token_and_not_a_descriptor() -> None:
    """Digest, location, media type, retention and redaction belong to PXK-63, not here."""
    declared = load_json(CONTRACTS.schema_path(MEASUREMENT))["properties"]["raw_artifact_ref"]
    assert declared["$ref"].endswith("#/$defs/id")
    assert set(declared) <= {"$ref", "description"}, (
        f"the reference grew a structure of its own: {sorted(declared)}"
    )


# --- open tokens stay open ----------------------------------------------------------------

OPEN_TOKENS = [
    (MEASUREMENT, "metric_id"),
    (MEASUREMENT, "collector"),
    (EVIDENCE, "scenario"),
    (EVIDENCE, "collector"),
]


@pytest.mark.parametrize(
    ("contract", "member"), OPEN_TOKENS, ids=[f"{c}/{m}" for c, m in OPEN_TOKENS]
)
def test_an_open_vocabulary_fixes_a_shape_and_never_a_set(contract: str, member: str) -> None:
    """A metric, a collector and a scenario a later slice introduces must validate unchanged."""
    declared = load_json(CONTRACTS.schema_path(contract))["properties"][member]
    assert "enum" not in declared and "const" not in declared, f"{contract}.{member} is closed"
    assert declared["$ref"].endswith("#/$defs/code")


# --- the shared block on its own ----------------------------------------------------------


def test_the_assessment_block_validates_independently_of_either_carrier() -> None:
    """A shared definition is still checkable in its own right, through the existing harness."""
    validator = CONTRACTS.validator_for_definition("assessment", shared=ASSESSMENT_SHARED)
    for assessment in PERFORMED + NOT_ASSESSED:
        assert list(validator.iter_errors(assessment)) == [], _id(assessment)
    assert list(validator.iter_errors({})), "an empty assessment states nothing and is not valid"


# --- determinism --------------------------------------------------------------------------


@pytest.mark.parametrize("assessment", PERFORMED + NOT_ASSESSED, ids=_id)
def test_the_same_document_validates_identically_twice(assessment: dict[str, str]) -> None:
    for contract, build in CARRIERS:
        document = build(assessment)
        assert CONTRACTS.validate(contract, document) == CONTRACTS.validate(contract, document)


# --- what the next slice needs ------------------------------------------------------------

#: The HTTP/HTML observations PXK-67 will actually make. Each is expressed here through the
#: contracts as they now stand, so "these contracts are sufficient for PXK-67" is a checked
#: statement rather than a claim in a report.
PXK67_OBSERVATIONS = [
    ("HTTP_STATUS", "INTEGER", "integer_value", 200),
    ("FINAL_URL", "URL", "url_value", "https://example.com/en/"),
    ("CONTENT_TYPE", "TEXT", "text_value", "text/html; charset=utf-8"),
    ("TRANSPORT_IS_HTTPS", "BOOLEAN", "boolean_value", True),
    ("PAGE_TITLE_PRESENT", "BOOLEAN", "boolean_value", True),
    ("PAGE_TITLE", "TEXT", "text_value", "Example Domain"),
    ("META_DESCRIPTION_PRESENT", "BOOLEAN", "boolean_value", False),
    ("META_DESCRIPTION", "TEXT", "text_value", "An illustrative domain for documentation."),
    ("CANONICAL_PRESENT", "BOOLEAN", "boolean_value", True),
    ("CANONICAL_URL", "URL", "url_value", "https://example.com/en/"),
]


@pytest.mark.parametrize(
    ("metric", "value_type", "member", "value"),
    PXK67_OBSERVATIONS,
    ids=[case[0] for case in PXK67_OBSERVATIONS],
)
def test_every_observation_the_next_slice_needs_is_representable(
    metric: str, value_type: str, member: str, value: Any
) -> None:
    document = measurement(
        PERFORMED_KNOWN[0], metric_id=metric, result={"value_type": value_type, member: value}
    )
    assert CONTRACTS.validate(MEASUREMENT, document) == ()


@pytest.mark.parametrize("reason", NOT_ASSESSED_REASONS)
def test_every_way_the_next_slice_can_fail_is_representable_without_touching_the_website(
    reason: str,
) -> None:
    """Each failure mode is a valid record that carries no value and no judgement."""
    document = measurement({"not_assessed_reason": reason}, metric_id="HTTP_STATUS")
    assert CONTRACTS.validate(MEASUREMENT, document) == ()
    assert "result" not in document
    assert ("", "not") in _keys(
        MEASUREMENT,
        measurement(
            {"not_assessed_reason": reason},
            result={"value_type": "BOOLEAN", "boolean_value": False},
        ),
    )
