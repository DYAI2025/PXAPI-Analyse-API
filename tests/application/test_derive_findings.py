"""Deriving findings from evidence: the chain, and everything that must break it.

Every finding this module produces is validated against the registered contract through the
same registry the service uses, so "it validates" means here what it means in production.
Above that sit the two properties no schema can assert on its own.

**The chain is finding -> evidence -> measurement, and it is load-bearing.** A finding is
emitted only when the evidence exists, belongs to this run, was itself established, references
the decisive measurement, and that measurement belongs to this run and established a value. Cut
any one of those links and the finding disappears rather than degrading into a claim with
nothing behind it.

**A technical failure is never a finding.** The neutrality matrix below is exhaustive over the
contracts' own vocabularies: every ``not_assessed_reason`` and every non-``KNOWN`` result state,
on the measurement and on the evidence, and on both at once. A timeout, a refused target, a
crashed parser and an assessment that established nothing all produce an empty list — never a
finding, and never a negative one.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import pytest

from pxapi.adapters.contracts.registry import ContractRegistry
from pxapi.application.derive_findings import derive_findings
from pxapi.config.contract_root import contract_root
from pxapi.domain.findings import RULES, FindingClass, RuleId
from pxapi.domain.observations import COLLECTOR, COLLECTOR_VERSION, SCENARIO_HOMEPAGE_FETCH, Metric
from tests.test_closed_vocabularies import NOT_ASSESSED_REASONS, RESULT_STATES

CONTRACTS = ContractRegistry(contract_root())
FINDING = "diagnostic-finding"

RUN = "run-0001"
OTHER_RUN = "run-0002"
SOURCE_URL = "https://example.test/"
OBSERVED_AT = "2026-09-07T10:00:01Z"

#: The four members that must not vary with a measured value.
TEXT_MEMBERS = ("finding_summary", "business_impact", "recommended_action", "limitation")

#: Result states that establish nothing about the site. ``KNOWN`` is deliberately excluded.
VALUELESS_STATES = [state for state in RESULT_STATES if state != "KNOWN"]


def counting_ids() -> Callable[[], str]:
    counter = {"n": 0}

    def new_id() -> str:
        counter["n"] += 1
        return f"fnd-{counter['n']:04d}"

    return new_id


def measurement(
    measurement_id: str,
    metric: Metric,
    assessment: dict[str, str],
    result: dict[str, Any] | None = None,
    run_id: str = RUN,
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "measurement_id": measurement_id,
        "metric_id": metric.value,
        "source_url": SOURCE_URL,
        "observed_at": OBSERVED_AT,
        "collector": COLLECTOR,
        "collector_version": COLLECTOR_VERSION,
        "assessment": dict(assessment),
    }
    if result is not None:
        document["result"] = result
    return document


def evidence(
    evidence_id: str,
    assessment: dict[str, str],
    measurement_refs: Sequence[str],
    run_id: str = RUN,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "evidence_id": evidence_id,
        "source_url": SOURCE_URL,
        "observed_at": OBSERVED_AT,
        "scenario": SCENARIO_HOMEPAGE_FETCH,
        "collector": COLLECTOR,
        "collector_version": COLLECTOR_VERSION,
        "assessment": dict(assessment),
        "measurement_refs": list(measurement_refs),
    }


KNOWN = {"collection_mode": "OBSERVED", "result_state": "KNOWN"}
MEASURED_KNOWN = {"collection_mode": "MEASURED", "result_state": "KNOWN"}


def one_fact(
    metric: Metric,
    result: dict[str, Any] | None,
    measurement_assessment: dict[str, str] | None = None,
    evidence_assessment: dict[str, str] | None = None,
    measurement_run: str = RUN,
    evidence_run: str = RUN,
    refs: Sequence[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """One measurement and the one piece of evidence that references it."""
    record = measurement(
        "msr-0001",
        metric,
        measurement_assessment if measurement_assessment is not None else MEASURED_KNOWN,
        result,
        run_id=measurement_run,
    )
    derived = evidence(
        "evd-0001",
        evidence_assessment if evidence_assessment is not None else KNOWN,
        ["msr-0001"] if refs is None else refs,
        run_id=evidence_run,
    )
    return [record], [derived]


def derive(
    measurements: Sequence[dict[str, Any]],
    evidence_documents: Sequence[dict[str, Any]],
    run_id: str = RUN,
) -> list[dict[str, Any]]:
    return derive_findings(run_id, measurements, evidence_documents, counting_ids())


def status(code: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return one_fact(Metric.HTTP_STATUS, {"value_type": "INTEGER", "integer_value": code})


def https(observed: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return one_fact(Metric.TRANSPORT_IS_HTTPS, {"value_type": "BOOLEAN", "boolean_value": observed})


def title_present(observed: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return one_fact(Metric.PAGE_TITLE_PRESENT, {"value_type": "BOOLEAN", "boolean_value": observed})


def generic_noindex(observed: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return one_fact(
        Metric.HOMEPAGE_GENERIC_NOINDEX_PRESENT,
        {"value_type": "BOOLEAN", "boolean_value": observed},
    )


def assert_all_valid(findings: Sequence[dict[str, Any]]) -> None:
    for document in findings:
        found = CONTRACTS.validate(FINDING, document)
        assert found == (), f"{document.get('rule_id')}: {[v.key for v in found]}"


# --- canaries --------------------------------------------------------------------------------


def test_the_contract_registry_is_the_real_one() -> None:
    """Without this, every validation below could be passing against an empty registry."""
    assert CONTRACTS.manifest_path.is_file()
    assert CONTRACTS.has_contract(FINDING)


def test_the_neutrality_matrix_is_not_empty() -> None:
    assert VALUELESS_STATES and NOT_ASSESSED_REASONS and len(RULES) == 4


# --- R1: the HTTP error rule -----------------------------------------------------------------


def test_an_error_status_produces_one_finding_bound_to_its_evidence() -> None:
    measurements, evidence_documents = status(503)
    findings = derive(measurements, evidence_documents)

    assert len(findings) == 1
    found = findings[0]
    assert_all_valid(findings)
    assert found["run_id"] == RUN
    assert found["rule_id"] == RuleId.HTTP_ERROR_RESPONSE
    assert found["rule_version"] == "1.0.0"
    assert found["finding_class"] == FindingClass.HOMEPAGE_HTTP_ERROR_STATUS
    assert found["evidence_refs"] == ["evd-0001"]


@pytest.mark.parametrize("code", [200, 204, 301, 302, 304, 399])
def test_a_status_below_the_threshold_produces_no_finding(code: int) -> None:
    measurements, evidence_documents = status(code)
    assert derive(measurements, evidence_documents) == []


@pytest.mark.parametrize("code", [400, 418, 503])
def test_a_status_at_or_above_the_threshold_produces_a_finding(code: int) -> None:
    measurements, evidence_documents = status(code)
    findings = derive(measurements, evidence_documents)
    assert [f["rule_id"] for f in findings] == [RuleId.HTTP_ERROR_RESPONSE]


def test_the_threshold_is_inclusive_at_four_hundred_end_to_end() -> None:
    assert derive(*status(399)) == []
    assert len(derive(*status(400))) == 1


def test_a_teapot_and_an_unavailable_service_read_identically() -> None:
    """The authoritative no-interpolation proof.

    418 and 503 are different measured facts and stay different in the measurement record. The
    finding is a fixed projection of the rule, so all four of its texts are byte-identical: a
    status can never leak into prose that no contract validates.
    """
    teapot = derive(*status(418))[0]
    unavailable = derive(*status(503))[0]

    for member in TEXT_MEMBERS:
        assert teapot[member] == unavailable[member], member
        assert "418" not in teapot[member] and "503" not in unavailable[member], member
    assert teapot["finding_class"] == unavailable["finding_class"]


# --- R2 and R3 -------------------------------------------------------------------------------


def test_a_transport_observed_as_plain_http_produces_a_finding() -> None:
    findings = derive(*https(False))
    assert_all_valid(findings)
    assert [f["rule_id"] for f in findings] == [RuleId.NON_HTTPS_FINAL_TRANSPORT]
    assert findings[0]["finding_class"] == FindingClass.HOMEPAGE_FINAL_TRANSPORT_NOT_HTTPS


def test_a_transport_observed_as_https_produces_no_finding() -> None:
    assert derive(*https(True)) == []


def test_a_title_observed_as_absent_produces_a_finding() -> None:
    findings = derive(*title_present(False))
    assert_all_valid(findings)
    assert [f["rule_id"] for f in findings] == [RuleId.MISSING_HOMEPAGE_TITLE]
    assert findings[0]["finding_class"] == FindingClass.HOMEPAGE_TITLE_MISSING


def test_a_title_observed_as_present_produces_no_finding() -> None:
    assert derive(*title_present(True)) == []


# --- R4: the generic noindex directive ---------------------------------------------------------


def test_a_generic_noindex_observed_as_present_produces_a_finding() -> None:
    findings = derive(*generic_noindex(True))
    assert_all_valid(findings)
    assert [f["rule_id"] for f in findings] == [RuleId.HOMEPAGE_EXPLICIT_NOINDEX]
    assert findings[0]["finding_class"] == FindingClass.HOMEPAGE_GENERIC_NOINDEX_DIRECTIVE
    assert findings[0]["rule_version"] == "1.0.0"
    assert findings[0]["evidence_refs"] == ["evd-0001"]


def test_a_generic_noindex_observed_as_absent_produces_no_finding() -> None:
    """The site was assessed and declares no such directive. That is not a finding."""
    assert derive(*generic_noindex(False)) == []


def test_a_generic_noindex_that_established_nothing_produces_no_finding() -> None:
    """The ``UNKNOWN`` combined result: an ambiguous header, or a read that stopped early.

    This is the case that separates R4 from the two absence rules. R2 and R3 fire on an
    established ``false``; R4 fires on an established ``true``, so the direction in which
    ``UNKNOWN`` must not be read is the opposite one — and it must not be read either way.
    """
    measurements, evidence_documents = one_fact(
        Metric.HOMEPAGE_GENERIC_NOINDEX_PRESENT,
        None,
        measurement_assessment={"collection_mode": "OBSERVED", "result_state": "UNKNOWN"},
        evidence_assessment={"collection_mode": "OBSERVED", "result_state": "UNKNOWN"},
    )
    assert derive(measurements, evidence_documents) == []


def test_a_channel_metric_alone_never_produces_the_finding() -> None:
    """R4 decides on the combined record, never on one channel's own observation.

    A rule reading a channel directly would emit a finding from half the evidence, and the
    other half is exactly what decides whether the directive applied generically at all.
    """
    for channel in (
        Metric.META_ROBOTS_GENERIC_NOINDEX_PRESENT,
        Metric.X_ROBOTS_TAG_GENERIC_NOINDEX_PRESENT,
    ):
        measurements, evidence_documents = one_fact(
            channel, {"value_type": "BOOLEAN", "boolean_value": True}
        )
        assert derive(measurements, evidence_documents) == [], channel


def test_the_r4_finding_never_names_where_the_directive_was_declared() -> None:
    """The channel is in the evidence, never in the prose.

    The word ``noindex`` is in the fixed text on purpose — it names the kind of directive the
    rule is about. What must never appear is anything that could only come from *this*
    observation: which channel carried it, or which crawler was addressed.
    """
    found = derive(*generic_noindex(True))[0]
    for member in TEXT_MEMBERS:
        lowered = found[member].lower()
        for leaked in ("x-robots-tag", "googlebot", "bingbot", "<meta", "header"):
            assert leaked not in lowered, f"{member}: {leaked}"


def test_an_overlong_but_present_title_is_not_a_missing_title() -> None:
    """The value could not be carried; the *presence* still could, and it says the title is there.

    This is the case that separates "the contract cannot represent this text" from "the site
    has no title". The collector records presence as KNOWN true and the title value as UNKNOWN,
    and R3 reads presence, so nothing fires.
    """
    over = "x" * (CONTRACTS.max_single_line_text() + 1)
    assert len(over) > CONTRACTS.max_single_line_text()
    measurements = [
        measurement(
            "msr-0001",
            Metric.PAGE_TITLE_PRESENT,
            KNOWN,
            {"value_type": "BOOLEAN", "boolean_value": True},
        ),
        # The value itself established nothing: it will not fit the contract. It carries no
        # result at all, which is exactly why it must not be read as an absence.
        measurement(
            "msr-0002",
            Metric.PAGE_TITLE,
            {"collection_mode": "OBSERVED", "result_state": "UNKNOWN"},
        ),
    ]
    evidence_documents = [
        evidence("evd-0001", KNOWN, ["msr-0001"]),
        evidence(
            "evd-0002", {"collection_mode": "OBSERVED", "result_state": "UNKNOWN"}, ["msr-0002"]
        ),
    ]
    assert derive(measurements, evidence_documents) == []


# --- the pinned emission order ---------------------------------------------------------------


def test_three_simultaneous_findings_are_emitted_in_the_pinned_rule_order() -> None:
    measurements = [
        measurement(
            "msr-0003",
            Metric.PAGE_TITLE_PRESENT,
            KNOWN,
            {"value_type": "BOOLEAN", "boolean_value": False},
        ),
        measurement(
            "msr-0002",
            Metric.TRANSPORT_IS_HTTPS,
            KNOWN,
            {"value_type": "BOOLEAN", "boolean_value": False},
        ),
        measurement(
            "msr-0001",
            Metric.HTTP_STATUS,
            MEASURED_KNOWN,
            {"value_type": "INTEGER", "integer_value": 500},
        ),
    ]
    evidence_documents = [
        evidence("evd-0003", KNOWN, ["msr-0003"]),
        evidence("evd-0002", KNOWN, ["msr-0002"]),
        evidence("evd-0001", KNOWN, ["msr-0001"]),
    ]
    findings = derive(measurements, evidence_documents)

    assert_all_valid(findings)
    assert [f["rule_id"] for f in findings] == [
        RuleId.HTTP_ERROR_RESPONSE,
        RuleId.NON_HTTPS_FINAL_TRANSPORT,
        RuleId.MISSING_HOMEPAGE_TITLE,
    ], "the emission order must be the pinned rule order, not the input order"
    assert [f["evidence_refs"] for f in findings] == [["evd-0001"], ["evd-0002"], ["evd-0003"]]


def test_every_rule_fires_at_once_in_the_pinned_order() -> None:
    """The full rule set, from evidence deliberately supplied in the reverse of that order."""
    facts = [
        (Metric.HOMEPAGE_GENERIC_NOINDEX_PRESENT, {"value_type": "BOOLEAN", "boolean_value": True}),
        (Metric.PAGE_TITLE_PRESENT, {"value_type": "BOOLEAN", "boolean_value": False}),
        (Metric.TRANSPORT_IS_HTTPS, {"value_type": "BOOLEAN", "boolean_value": False}),
        (Metric.HTTP_STATUS, {"value_type": "INTEGER", "integer_value": 500}),
    ]
    measurements = [
        measurement(f"msr-{index:04d}", metric, KNOWN, result)
        for index, (metric, result) in enumerate(facts, start=1)
    ]
    evidence_documents = [
        evidence(f"evd-{index:04d}", KNOWN, [f"msr-{index:04d}"])
        for index in range(1, len(facts) + 1)
    ]
    findings = derive(measurements, evidence_documents)

    assert_all_valid(findings)
    assert [f["rule_id"] for f in findings] == [rule.rule_id for rule in RULES]
    assert len(findings) == len(RULES)


# --- a technical failure is never a finding --------------------------------------------------

TRIGGERING_FACTS = {
    "http-error": (Metric.HTTP_STATUS, {"value_type": "INTEGER", "integer_value": 503}),
    "not-https": (Metric.TRANSPORT_IS_HTTPS, {"value_type": "BOOLEAN", "boolean_value": False}),
    "no-title": (Metric.PAGE_TITLE_PRESENT, {"value_type": "BOOLEAN", "boolean_value": False}),
    "generic-noindex": (
        Metric.HOMEPAGE_GENERIC_NOINDEX_PRESENT,
        {"value_type": "BOOLEAN", "boolean_value": True},
    ),
}
FACT_IDS = sorted(TRIGGERING_FACTS)


def test_each_triggering_fact_really_does_trigger() -> None:
    """Canary: the neutrality matrix proves nothing unless the same facts fire when healthy."""
    for name in FACT_IDS:
        metric, result = TRIGGERING_FACTS[name]
        assert len(derive(*one_fact(metric, result))) == 1, name


@pytest.mark.parametrize("reason", NOT_ASSESSED_REASONS)
@pytest.mark.parametrize("fact", FACT_IDS)
def test_a_measurement_that_never_happened_produces_no_finding(fact: str, reason: str) -> None:
    """A provider failure, our own crash, a refused permission or a timeout says nothing here."""
    metric, _ = TRIGGERING_FACTS[fact]
    measurements, evidence_documents = one_fact(
        metric,
        None,
        measurement_assessment={"not_assessed_reason": reason},
        evidence_assessment={"not_assessed_reason": reason},
    )
    assert derive(measurements, evidence_documents) == []


@pytest.mark.parametrize("state", VALUELESS_STATES)
@pytest.mark.parametrize("fact", FACT_IDS)
def test_a_measurement_that_established_nothing_produces_no_finding(fact: str, state: str) -> None:
    """UNKNOWN, CONFLICT and NOT_APPLICABLE are outcomes about the assessment, not the site."""
    metric, _ = TRIGGERING_FACTS[fact]
    assessment = {"collection_mode": "OBSERVED", "result_state": state}
    measurements, evidence_documents = one_fact(
        metric, None, measurement_assessment=assessment, evidence_assessment=assessment
    )
    assert derive(measurements, evidence_documents) == []


@pytest.mark.parametrize("state", VALUELESS_STATES)
@pytest.mark.parametrize("fact", FACT_IDS)
def test_evidence_that_established_nothing_cannot_carry_a_finding(fact: str, state: str) -> None:
    """Even with a measurement that fires, the evidence gate has to have been passed."""
    metric, result = TRIGGERING_FACTS[fact]
    measurements, evidence_documents = one_fact(
        metric, result, evidence_assessment={"collection_mode": "OBSERVED", "result_state": state}
    )
    assert derive(measurements, evidence_documents) == []


@pytest.mark.parametrize("reason", NOT_ASSESSED_REASONS)
@pytest.mark.parametrize("fact", FACT_IDS)
def test_evidence_that_was_never_assessed_cannot_carry_a_finding(fact: str, reason: str) -> None:
    metric, result = TRIGGERING_FACTS[fact]
    measurements, evidence_documents = one_fact(
        metric, result, evidence_assessment={"not_assessed_reason": reason}
    )
    assert derive(measurements, evidence_documents) == []


@pytest.mark.parametrize("reason", NOT_ASSESSED_REASONS)
@pytest.mark.parametrize("fact", FACT_IDS)
def test_a_measurement_that_was_never_assessed_cannot_produce_a_finding(
    fact: str, reason: str
) -> None:
    """Even where the evidence claims KNOWN, an unmeasured fact cannot become a conclusion."""
    metric, _ = TRIGGERING_FACTS[fact]
    measurements, evidence_documents = one_fact(
        metric, None, measurement_assessment={"not_assessed_reason": reason}
    )
    assert derive(measurements, evidence_documents) == []


# --- the evidence chain must hold ------------------------------------------------------------


@pytest.mark.parametrize("fact", FACT_IDS)
def test_a_finding_cannot_rest_on_a_dangling_measurement_reference(fact: str) -> None:
    """The evidence names a measurement nobody produced, so there is nothing behind the claim."""
    metric, result = TRIGGERING_FACTS[fact]
    measurements, evidence_documents = one_fact(metric, result, refs=["msr-does-not-exist"])
    assert derive(measurements, evidence_documents) == []


@pytest.mark.parametrize("fact", FACT_IDS)
def test_a_finding_cannot_rest_on_a_measurement_from_another_run(fact: str) -> None:
    """A conclusion assembled across two runs describes a site that never existed at one instant."""
    metric, result = TRIGGERING_FACTS[fact]
    measurements, evidence_documents = one_fact(metric, result, measurement_run=OTHER_RUN)
    assert derive(measurements, evidence_documents) == []


@pytest.mark.parametrize("fact", FACT_IDS)
def test_evidence_from_another_run_cannot_carry_a_finding_into_this_one(fact: str) -> None:
    metric, result = TRIGGERING_FACTS[fact]
    measurements, evidence_documents = one_fact(metric, result, evidence_run=OTHER_RUN)
    assert derive(measurements, evidence_documents) == []


@pytest.mark.parametrize("fact", FACT_IDS)
def test_a_measurement_no_evidence_references_produces_no_finding(fact: str) -> None:
    """The chain runs through evidence. A raw measurement is not a licence to conclude."""
    metric, result = TRIGGERING_FACTS[fact]
    measurements, _ = one_fact(metric, result)
    assert derive(measurements, []) == []


@pytest.mark.parametrize("fact", FACT_IDS)
def test_evidence_that_references_a_different_measurement_produces_no_finding(fact: str) -> None:
    """Detached: the decisive record exists and fires, but this evidence does not rest on it."""
    metric, result = TRIGGERING_FACTS[fact]
    decisive = measurement("msr-0001", metric, MEASURED_KNOWN, result)
    unrelated = measurement(
        "msr-0002",
        Metric.REDIRECT_COUNT,
        MEASURED_KNOWN,
        {"value_type": "INTEGER", "integer_value": 0},
    )
    detached = evidence("evd-0001", KNOWN, ["msr-0002"])
    assert derive([decisive, unrelated], [detached]) == []


@pytest.mark.parametrize("fact", FACT_IDS)
def test_a_record_that_contradicts_itself_is_not_trusted_for_a_finding(fact: str) -> None:
    """Defence in depth: the derivation does not infer the assessment from the value.

    The contracts refuse a record that says both "never assessed" and "here is the value", so
    such a document can only arrive from a defect upstream of here. It must still produce no
    finding: reading the value because it happens to be present would make the assessment
    advisory, and the assessment is the member that decides whether anything about the site may
    be stated at all.
    """
    metric, result = TRIGGERING_FACTS[fact]
    contradictory = measurement(
        "msr-0001", metric, {"not_assessed_reason": "PROVIDER_FAILURE"}, result
    )
    assert CONTRACTS.validate("measurement-record", contradictory), (
        "canary: this document must be one the contract itself refuses"
    )
    assert derive([contradictory], [evidence("evd-0001", KNOWN, ["msr-0001"])]) == []


def test_the_decisive_measurement_must_be_the_metric_the_rule_decides_on() -> None:
    """A status of 503 recorded under another metric is not an HTTP error finding."""
    measurements, evidence_documents = one_fact(
        Metric.REDIRECT_COUNT, {"value_type": "INTEGER", "integer_value": 503}
    )
    assert derive(measurements, evidence_documents) == []


def test_the_emitted_finding_resolves_the_whole_chain_back_to_the_measured_value() -> None:
    """finding -> evidence_id -> measurement_id -> the value that actually decided it."""
    measurements, evidence_documents = status(503)
    found = derive(measurements, evidence_documents)[0]

    by_evidence = {e["evidence_id"]: e for e in evidence_documents}
    by_measurement = {m["measurement_id"]: m for m in measurements}

    assert len(found["evidence_refs"]) == 1
    resolved_evidence = by_evidence[found["evidence_refs"][0]]
    assert resolved_evidence["run_id"] == found["run_id"]
    assert resolved_evidence["assessment"]["result_state"] == "KNOWN"

    assert len(resolved_evidence["measurement_refs"]) == 1
    resolved_measurement = by_measurement[resolved_evidence["measurement_refs"][0]]
    assert resolved_measurement["run_id"] == found["run_id"]
    assert resolved_measurement["metric_id"] == Metric.HTTP_STATUS
    assert resolved_measurement["result"]["integer_value"] == 503


# --- emptiness, and determinism --------------------------------------------------------------


def test_a_run_with_nothing_measured_yields_an_empty_list_rather_than_a_negative_finding() -> None:
    assert derive([], []) == []


def test_the_same_frozen_input_derives_the_same_findings_twice() -> None:
    measurements, evidence_documents = status(503)
    assert derive(measurements, evidence_documents) == derive(measurements, evidence_documents)


def test_deriving_never_mutates_the_documents_it_reads() -> None:
    measurements, evidence_documents = status(503)
    import copy

    before = copy.deepcopy((measurements, evidence_documents))
    derive(measurements, evidence_documents)
    assert (measurements, evidence_documents) == before


def test_every_rule_emits_a_finding_that_satisfies_the_registered_contract() -> None:
    """All three rules' fixed texts fit the contract's bounds, not merely the one we sampled."""
    emitted = []
    for name in FACT_IDS:
        metric, result = TRIGGERING_FACTS[name]
        emitted.extend(derive(*one_fact(metric, result)))
    assert len(emitted) == len(RULES)
    assert_all_valid(emitted)
