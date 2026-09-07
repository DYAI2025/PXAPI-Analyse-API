"""The Diagnostic Finding contract: a derived projection that can never outrun its evidence.

A finding is not a measurement and not evidence. It is the first document in this registry that
is allowed to say something *about* a website in ordinary language, so the rules that keep it
honest are structural here rather than editorial:

* ``evidence_refs`` is the Fact Authority. It is required, non-empty and unique, so a finding
  that names nothing it rests on is not representable at all.
* the four product texts are bounded single-line values. They are fixed per rule, so the
  contract's job is only to refuse a text that could not be rendered or logged safely.
* the closed root refuses every member a scoring, severity, priority, confidence or customer
  projection model would need. Those are later, separately authorised decisions, and a finding
  that could carry them would pre-empt them.

Nothing here restates a rule a generic registry test already owns — closure, version pinning,
example validity, pattern anchoring and the invalid fixtures each have their own module.
"""

from __future__ import annotations

import pytest

from tests.contracts.support import CONTRACTS, load_json

FINDING = "diagnostic-finding"

#: The exact root membership this version admits. Stated in full rather than as a subset: a
#: member added or dropped without a deliberate version decision fails here.
ROOT_MEMBERS: tuple[str, ...] = (
    "schema_version",
    "run_id",
    "finding_id",
    "rule_id",
    "rule_version",
    "finding_class",
    "evidence_refs",
    "finding_summary",
    "business_impact",
    "recommended_action",
    "limitation",
)

#: The deterministic derived projections. Each is a product text, never a measured value.
PROJECTION_TEXTS: tuple[str, ...] = (
    "finding_summary",
    "business_impact",
    "recommended_action",
    "limitation",
)

#: Members a scoring, severity, ranking, confidence or customer-projection model would need.
#: None of those exists yet, and a finding that could carry one would decide them by accident.
OUT_OF_SCOPE_MEMBERS: tuple[str, ...] = (
    "score",
    "score_value",
    "severity",
    "priority",
    "rank",
    "confidence",
    "weight",
    "overall_intervention_level",
    "customer_facing",
    "polarity",
    "measurement_refs",
)


def schema() -> dict:
    return load_json(CONTRACTS.schema_path(FINDING))


def finding(**overrides: object) -> dict:
    document: dict[str, object] = {
        "schema_version": CONTRACTS.entry(FINDING)["version"],
        "run_id": "run-01JQ8Z4K2M0000000000000001",
        "finding_id": "fnd-01JQ8Z4K2M0000000000000001",
        "rule_id": "HTTP_ERROR_RESPONSE",
        "rule_version": "1.0.0",
        "finding_class": "HOMEPAGE_HTTP_ERROR_STATUS",
        "evidence_refs": ["evd-01JQ8Z4K2M0000000000000001"],
        "finding_summary": "A single-line summary of what was observed.",
        "business_impact": "A bounded, general statement of what this could mean commercially.",
        "recommended_action": "A single-line action the site owner can take.",
        "limitation": "What this finding deliberately does not establish.",
    }
    document.update(overrides)
    return document


def keys(document: dict) -> set[tuple[str, str]]:
    return {violation.key for violation in CONTRACTS.validate(FINDING, document)}


# --- the contract exists, and this slice owns it ---------------------------------------------


def test_the_contract_is_registered_as_an_active_core_contract() -> None:
    entry = CONTRACTS.entry(FINDING)
    assert entry["version"] == "1.0.0"
    assert entry["role"] == "core"
    assert entry["status"] == "active"


def test_the_owning_slice_is_the_jira_item_and_not_the_implementation_label() -> None:
    """``PXK-20.A`` is a bounded implementation slice, not a Jira key. The owner is the item."""
    assert CONTRACTS.entry(FINDING)["owner_slice"] == "PXK-20"


def test_the_baseline_finding_validates() -> None:
    """Canary: every negative proof below is only meaningful against a document that passes."""
    assert CONTRACTS.validate(FINDING, finding()) == ()


# --- the root membership ---------------------------------------------------------------------


def test_the_root_declares_and_requires_exactly_these_members() -> None:
    declared = schema()
    assert tuple(declared["properties"]) == ROOT_MEMBERS
    assert tuple(declared["required"]) == ROOT_MEMBERS


@pytest.mark.parametrize("member", ROOT_MEMBERS)
def test_every_member_is_required(member: str) -> None:
    document = finding()
    del document[member]
    assert ("", "required") in keys(document), member


@pytest.mark.parametrize("member", OUT_OF_SCOPE_MEMBERS)
def test_the_closed_root_refuses_a_scoring_or_projection_member(member: str) -> None:
    """No score, no severity, no ranking, no confidence, no customer projection — and no
    shortcut past the evidence: a finding may not name a measurement directly."""
    assert member not in schema()["properties"], f"{member} is declared; this slice adds none"
    assert ("", "additionalProperties") in keys(finding(**{member: "anything"}))


# --- evidence is the Fact Authority ----------------------------------------------------------


def test_evidence_refs_is_a_non_empty_unique_list_of_opaque_identifiers() -> None:
    declared = schema()["properties"]["evidence_refs"]
    assert declared["type"] == "array"
    assert declared["minItems"] == 1
    assert declared["uniqueItems"] is True
    assert declared["items"]["$ref"].endswith("#/$defs/id")


def test_a_finding_that_rests_on_nothing_is_not_representable() -> None:
    assert ("/evidence_refs", "minItems") in keys(finding(evidence_refs=[]))


def test_a_repeated_evidence_reference_is_refused() -> None:
    """One evidence document counted twice would overstate what the finding rests on."""
    repeated = ["evd-01JQ8Z4K2M0000000000000001", "evd-01JQ8Z4K2M0000000000000001"]
    assert ("/evidence_refs", "uniqueItems") in keys(finding(evidence_refs=repeated))


def test_several_distinct_evidence_references_are_accepted() -> None:
    both = ["evd-01JQ8Z4K2M0000000000000001", "evd-01JQ8Z4K2M0000000000000002"]
    assert CONTRACTS.validate(FINDING, finding(evidence_refs=both)) == ()


# --- the derived texts -----------------------------------------------------------------------


@pytest.mark.parametrize("member", PROJECTION_TEXTS)
def test_each_projection_text_is_a_bounded_single_line_value(member: str) -> None:
    assert schema()["properties"][member]["$ref"].endswith("#/$defs/single_line_text")


@pytest.mark.parametrize("member", PROJECTION_TEXTS)
def test_a_blank_projection_text_is_refused(member: str) -> None:
    """A finding with an empty product text is a finding nobody can act on."""
    assert (f"/{member}", "pattern") in keys(finding(**{member: ""}))


@pytest.mark.parametrize("member", PROJECTION_TEXTS)
def test_a_multiline_projection_text_is_refused(member: str) -> None:
    text = "First line.\nSecond line."
    assert (f"/{member}", "pattern") in keys(finding(**{member: text}))


@pytest.mark.parametrize("member", PROJECTION_TEXTS)
def test_a_projection_text_beyond_the_shared_bound_is_refused(member: str) -> None:
    over = "x" * (CONTRACTS.max_single_line_text() + 1)
    assert (f"/{member}", "maxLength") in keys(finding(**{member: over}))


# --- the rule identity -----------------------------------------------------------------------


@pytest.mark.parametrize("member", ("rule_id", "finding_class"))
def test_the_rule_identity_is_an_open_token_and_never_a_closed_set(member: str) -> None:
    """A rule a later slice adds must validate here without a contract change."""
    declared = schema()["properties"][member]
    assert "enum" not in declared and "const" not in declared, f"{member} is closed"
    assert declared["$ref"].endswith("#/$defs/code")
    assert CONTRACTS.validate(FINDING, finding(**{member: "A_RULE_NO_SLICE_HAS_WRITTEN_YET"})) == ()


@pytest.mark.parametrize("member", ("rule_id", "finding_class"))
def test_the_rule_identity_stays_a_token_rather_than_prose(member: str) -> None:
    assert (f"/{member}", "pattern") in keys(finding(**{member: "http error response"}))


def test_the_rule_version_travels_with_the_finding() -> None:
    """Two findings are comparable only when the rule behind them is the same version."""
    assert schema()["properties"]["rule_version"]["$ref"].endswith("#/$defs/single_line_label")
    assert ("/rule_version", "pattern") in keys(finding(rule_version=""))
