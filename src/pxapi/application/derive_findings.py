"""Turning established evidence into actionable findings, and refusing to do so otherwise.

This is the one place where a measured fact becomes a statement about a website, so it is where
the chain is enforced:

    DiagnosticFinding.evidence_refs
        -> WebsiteEvidence.evidence_id
            -> WebsiteEvidence.measurement_refs
                -> MeasurementRecord.measurement_id

Five conditions must all hold before a finding exists, and each is checked here rather than
assumed from how the collector happens to build its documents:

* the evidence belongs to this run;
* the evidence was itself established — a performed assessment with a ``KNOWN`` result;
* the decisive measurement record exists;
* the evidence actually references it;
* the measurement belongs to this run and established a value.

Cut any one link and the finding is not emitted. There is deliberately no path from a raw
measurement to a conclusion: website evidence is where a statement about a site is allowed to be
made at all, and a finding that pointed straight at a measurement would bypass that gate.

**A technical failure is never a finding.** A provider failure, a timeout, a refused permission,
our own crashed runtime, an assessment that established nothing, an unresolved conflict and a
measurement that does not apply all fail the gate above, so they produce an empty list. Empty
means "these rules emitted nothing" — never that the site is fine.

**No measured value reaches a product text.** The texts come from the rule verbatim; this module
performs no formatting at all. That is why a 418 and a 503 produce byte-identical findings.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from pxapi.domain.findings import RULES, FindingRule

#: The one result state that establishes something about the analysed site. Everything else is
#: an outcome about the assessment, and a finding may never be built on one.
ESTABLISHED = "KNOWN"

#: The contract version every finding this module produces declares.
FINDING_SCHEMA_VERSION = "1.0.0"


def _established(document: Mapping[str, Any]) -> bool:
    """Whether a measurement or a piece of evidence actually established something.

    A document that was never assessed carries no ``result_state`` at all, so it falls out here
    with the same answer as one whose assessment ran and established nothing. Both are outcomes
    about the analysis, and neither may be read as a fact about the site.
    """
    assessment = document.get("assessment")
    if not isinstance(assessment, Mapping):
        return False
    return assessment.get("result_state") == ESTABLISHED


def _decisive_result(
    rule: FindingRule,
    evidence: Mapping[str, Any],
    measurements_in_run: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    """The result block of the measurement that decides ``rule`` for this evidence.

    ``None`` whenever the chain does not hold: the evidence references nothing this run
    produced, the referenced record is about another metric, or it established no value.
    """
    for reference in evidence.get("measurement_refs", ()):
        measurement = measurements_in_run.get(reference)
        if measurement is None:
            # A dangling reference, or a record belonging to another run: either way there is
            # nothing behind the claim this rule would make.
            continue
        if measurement.get("metric_id") != rule.metric.value:
            continue
        if not _established(measurement):
            continue
        result = measurement.get("result")
        if isinstance(result, Mapping):
            return result
    return None


def derive_findings(
    run_id: str,
    measurements: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
    new_id: Callable[[], str],
) -> list[dict[str, Any]]:
    """Every finding the authorised rules emit for one run, in the pinned rule order.

    The rules are the outer loop and the evidence the inner one, so the sequence is a property
    of the rule set rather than of the order documents happened to be built in. Nothing here is
    mutated: both inputs are read only.
    """
    measurements_in_run = {
        record["measurement_id"]: record
        for record in measurements
        if record.get("run_id") == run_id
    }
    eligible = [
        document
        for document in evidence
        if document.get("run_id") == run_id and _established(document)
    ]

    findings: list[dict[str, Any]] = []
    for rule in RULES:
        for document in eligible:
            result = _decisive_result(rule, document, measurements_in_run)
            if result is None or not rule.triggers(result):
                continue
            findings.append(
                {
                    "schema_version": FINDING_SCHEMA_VERSION,
                    "run_id": run_id,
                    "finding_id": new_id(),
                    "rule_id": rule.rule_id.value,
                    "rule_version": rule.rule_version,
                    "finding_class": rule.finding_class.value,
                    "evidence_refs": [document["evidence_id"]],
                    # Verbatim from the rule. No formatting step exists here, so no measured
                    # value can enter a text that no contract validates.
                    "finding_summary": rule.finding_summary,
                    "business_impact": rule.business_impact,
                    "recommended_action": rule.recommended_action,
                    "limitation": rule.limitation,
                }
            )
    return findings
