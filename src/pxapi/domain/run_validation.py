"""The vocabulary of run validation, and the two decisions it makes (PXAPI-25).

An Analysis Run that finished ``SUCCEEDED`` has executed; it has not thereby been shown to be a
result anyone may rely on. ``analysis-validation-receipt.v1`` is the separate statement about
that, and this module is its domain side: the seven gate families, the four gate states, the
closed set of reasons a gate may give, and two rules — which state a gate is in given its
reasons, and which state the run's validation is in given its gates.

Three decisions live here, and each is a business decision rather than a transport detail.

**A reason carries its own effect.** Every reason code is either a defect of this service
(``FAIL``), a missing, incomplete or technically unavailable piece of evidence (``BLOCKED``), or
the statement that a gate does not apply to this run (``NOT_APPLICABLE``). A gate's state is
*derived* from its reasons — no reason means the gate was checked and holds — so a gate can
never state ``PASS`` while naming a problem, and no producer decides a gate state by hand.

**Precedence is ``FAIL > BLOCKED > PASS``, and ``NOT_APPLICABLE`` is neutral.** One defect makes
the validation ``FAIL`` whatever else holds; otherwise one blocked gate makes it ``BLOCKED``.
A validation in which no gate was applicable established nothing and is ``BLOCKED`` rather than
``PASS``: a release nobody checked is not a release.

**Nothing technical is a verdict about the website.** Every ``BLOCKED`` reason names our process
— a bound we declared, a fetch that did not complete, an assessment that established nothing —
and none of them describes the site. That is why the reason vocabulary is closed: an open token
could arrive carrying a reason that describes the website instead, which is the same argument
that closes every other neutrality vocabulary in the registry.

Validation never changes Analysis Truth: nothing here reads or writes a canonical document, and
the receipt is a statement *about* a run, never a member of it.

Standard library only. The domain ring imports no third-party distribution at all.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

from pxapi.domain.acquisition_semantics import SemanticViolation
from pxapi.domain.run_state import RunState

#: The registered contract these rules are about.
ANALYSIS_VALIDATION_RECEIPT: Final = "analysis-validation-receipt"


class GateFamily(StrEnum):
    """The seven run-level gate families of validation v1, in the order they are reported."""

    #: The request the run executed is a valid request, bound to this run and its budget.
    INPUT_CONTRACT = "INPUT_CONTRACT"
    #: The run acquired the selection it planned, and the selection covered the site.
    ACQUISITION_COMPLETENESS = "ACQUISITION_COMPLETENESS"
    #: Every canonical document satisfies its registered contract and its contract semantics.
    CANONICAL_VALIDITY = "CANONICAL_VALIDITY"
    #: Every document is bound to this run, and every reference resolves once and only once.
    PROVENANCE_LINKAGE = "PROVENANCE_LINKAGE"
    #: Every acquired page is evidenced, and nothing the run measured is left without evidence.
    EVIDENCE_COVERAGE = "EVIDENCE_COVERAGE"
    #: No conflict is left unresolved, and no discovery limitation is left unstated.
    UNRESOLVED_CONFLICTS_LIMITATIONS = "UNRESOLVED_CONFLICTS_LIMITATIONS"
    #: The published artifact bundle is exactly the canonical documents, byte for byte.
    ARTIFACT_BUNDLE_VALIDITY = "ARTIFACT_BUNDLE_VALIDITY"


class GateState(StrEnum):
    """What one gate established. The first three are also the overall states."""

    #: The gate was actually checked and holds.
    PASS = "PASS"
    #: A defect of this service: a contract, invariant, linkage or bundle defect.
    FAIL = "FAIL"
    #: A reliable release cannot be established, because evidence is missing, incomplete or
    #: technically unavailable. Never a statement about the website.
    BLOCKED = "BLOCKED"
    #: The gate is deliberately not relevant to this run.
    NOT_APPLICABLE = "NOT_APPLICABLE"


#: The states the run's validation as a whole can be in. ``NOT_APPLICABLE`` is neutral and is
#: never an overall state; the order is the precedence, strongest first.
OVERALL_STATES: Final[tuple[GateState, ...]] = (GateState.FAIL, GateState.BLOCKED, GateState.PASS)


class ReasonCode(StrEnum):
    """Every reason a gate may give. Closed; see :data:`REASONS` for effect and ownership."""

    # --- defects of this service ------------------------------------------------------------
    REQUEST_MISSING = "REQUEST_MISSING"
    REQUEST_CONTRACT_INVALID = "REQUEST_CONTRACT_INVALID"
    REQUEST_NOT_BOUND_TO_RUN = "REQUEST_NOT_BOUND_TO_RUN"
    DECLARED_BUDGET_NOT_APPLIED = "DECLARED_BUDGET_NOT_APPLIED"
    RUN_STATE_UNAVAILABLE = "RUN_STATE_UNAVAILABLE"
    RUN_NOT_TERMINAL = "RUN_NOT_TERMINAL"
    RUN_FAILED_BY_PRODUCER_DEFECT = "RUN_FAILED_BY_PRODUCER_DEFECT"
    RUN_FAILURE_UNCLASSIFIED = "RUN_FAILURE_UNCLASSIFIED"
    ACQUISITION_RECORDS_MISSING = "ACQUISITION_RECORDS_MISSING"
    CANONICAL_MEMBER_MISSING = "CANONICAL_MEMBER_MISSING"
    CANONICAL_MEMBER_UNEXPECTED = "CANONICAL_MEMBER_UNEXPECTED"
    DOCUMENT_CONTAINER_INVALID = "DOCUMENT_CONTAINER_INVALID"
    DOCUMENT_CONTRACT_INVALID = "DOCUMENT_CONTRACT_INVALID"
    DOCUMENT_SEMANTICS_INVALID = "DOCUMENT_SEMANTICS_INVALID"
    PRODUCER_INVARIANT_BROKEN = "PRODUCER_INVARIANT_BROKEN"
    RUN_BINDING_BROKEN = "RUN_BINDING_BROKEN"
    LINKED_DOCUMENT_MISSING = "LINKED_DOCUMENT_MISSING"
    SELECTION_BINDING_BROKEN = "SELECTION_BINDING_BROKEN"
    ACQUISITION_LINKAGE_BROKEN = "ACQUISITION_LINKAGE_BROKEN"
    DUPLICATE_IDENTIFIER = "DUPLICATE_IDENTIFIER"
    BUNDLE_FILE_MISSING = "BUNDLE_FILE_MISSING"
    BUNDLE_FILE_UNEXPECTED = "BUNDLE_FILE_UNEXPECTED"
    BUNDLE_FILE_NOT_JSON = "BUNDLE_FILE_NOT_JSON"
    BUNDLE_FILE_DIFFERS_FROM_CANONICAL = "BUNDLE_FILE_DIFFERS_FROM_CANONICAL"
    VALIDATION_NOT_EVALUABLE = "VALIDATION_NOT_EVALUABLE"
    # --- missing, incomplete or technically unavailable evidence -----------------------------
    RUN_FAILED_TECHNICALLY = "RUN_FAILED_TECHNICALLY"
    RUN_CANCELLED = "RUN_CANCELLED"
    SELECTION_INCOMPLETE = "SELECTION_INCOMPLETE"
    PAGE_NOT_ACQUIRED = "PAGE_NOT_ACQUIRED"
    PAGE_BODY_TRUNCATED = "PAGE_BODY_TRUNCATED"
    PAGE_BODY_NOT_DECODED = "PAGE_BODY_NOT_DECODED"
    PAGE_MEASUREMENTS_WITHHELD = "PAGE_MEASUREMENTS_WITHHELD"
    PAGE_EVIDENCE_NOT_ASSESSED = "PAGE_EVIDENCE_NOT_ASSESSED"
    PAGE_EVIDENCE_UNKNOWN = "PAGE_EVIDENCE_UNKNOWN"
    MEASUREMENT_WITHOUT_EVIDENCE = "MEASUREMENT_WITHOUT_EVIDENCE"
    UNRESOLVED_CONFLICT = "UNRESOLVED_CONFLICT"
    DISCOVERY_SOURCE_LIMITED = "DISCOVERY_SOURCE_LIMITED"
    # --- the gate does not apply ---------------------------------------------------------------
    RUN_EMITTED_NO_PAGE_DOCUMENTS = "RUN_EMITTED_NO_PAGE_DOCUMENTS"
    REQUEST_WITHHELD_BY_POLICY = "REQUEST_WITHHELD_BY_POLICY"


@dataclass(frozen=True)
class ReasonSpec:
    """What one reason code does to its gate, which gates may give it, and what it says."""

    #: ``FAIL``, ``BLOCKED`` or ``NOT_APPLICABLE`` — never ``PASS``: a reason is a problem or an
    #: exemption, and a gate that holds gives none.
    effect: GateState
    #: The gate families allowed to give this reason.
    families: frozenset[GateFamily]
    #: One fixed sentence for a human reader. Never derived from input.
    meaning: str


_F = GateFamily
_ALL_FAMILIES: Final = frozenset(GateFamily)


def _spec(effect: GateState, meaning: str, *families: GateFamily) -> ReasonSpec:
    return ReasonSpec(effect, frozenset(families), meaning)


#: ``reason code -> effect, owning gate families, meaning``. The single statement of the reason
#: vocabulary: the contract's three reason-code enums are derived from it and pinned against it.
REASONS: Final[dict[ReasonCode, ReasonSpec]] = {
    ReasonCode.REQUEST_MISSING: _spec(
        GateState.FAIL,
        "The run carries no request document, so what it executed cannot be checked.",
        _F.INPUT_CONTRACT,
    ),
    ReasonCode.REQUEST_CONTRACT_INVALID: _spec(
        GateState.FAIL,
        "The request document does not satisfy its registered contract.",
        _F.INPUT_CONTRACT,
    ),
    ReasonCode.REQUEST_NOT_BOUND_TO_RUN: _spec(
        GateState.FAIL,
        "The request document belongs to a different run than the one validated.",
        _F.INPUT_CONTRACT,
    ),
    ReasonCode.DECLARED_BUDGET_NOT_APPLIED: _spec(
        GateState.FAIL,
        "The sampling manifest does not carry the page budget the operator declared.",
        _F.INPUT_CONTRACT,
    ),
    ReasonCode.RUN_STATE_UNAVAILABLE: _spec(
        GateState.FAIL,
        "The run carries no readable run state, so whether it executed cannot be checked.",
        _F.ACQUISITION_COMPLETENESS,
    ),
    ReasonCode.RUN_NOT_TERMINAL: _spec(
        GateState.FAIL,
        "The run is not in a terminal state, so there is no completed result to validate.",
        _F.ACQUISITION_COMPLETENESS,
    ),
    ReasonCode.RUN_FAILED_BY_PRODUCER_DEFECT: _spec(
        GateState.FAIL,
        "The run failed because this service built documents it may not emit.",
        _F.ACQUISITION_COMPLETENESS,
    ),
    ReasonCode.RUN_FAILURE_UNCLASSIFIED: _spec(
        GateState.FAIL,
        "The run failed with a code this validator cannot classify; the gap is ours.",
        _F.ACQUISITION_COMPLETENESS,
    ),
    ReasonCode.ACQUISITION_RECORDS_MISSING: _spec(
        GateState.FAIL,
        "A succeeded run carries no sampling manifest or no acquisition records.",
        _F.ACQUISITION_COMPLETENESS,
    ),
    ReasonCode.CANONICAL_MEMBER_MISSING: _spec(
        GateState.FAIL,
        "A canonical document this run must emit is missing.",
        _F.CANONICAL_VALIDITY,
    ),
    ReasonCode.CANONICAL_MEMBER_UNEXPECTED: _spec(
        GateState.FAIL,
        "The run carries a member that is not a canonical document of this analysis.",
        _F.CANONICAL_VALIDITY,
    ),
    ReasonCode.DOCUMENT_CONTAINER_INVALID: _spec(
        GateState.FAIL,
        "A canonical member is not in the container shape its documents are published in.",
        _F.CANONICAL_VALIDITY,
    ),
    ReasonCode.DOCUMENT_CONTRACT_INVALID: _spec(
        GateState.FAIL,
        "A canonical document does not satisfy its registered contract.",
        _F.CANONICAL_VALIDITY,
    ),
    ReasonCode.DOCUMENT_SEMANTICS_INVALID: _spec(
        GateState.FAIL,
        "A canonical document breaks a contract rule JSON Schema cannot state.",
        _F.CANONICAL_VALIDITY,
    ),
    ReasonCode.PRODUCER_INVARIANT_BROKEN: _spec(
        GateState.FAIL,
        "A canonical document breaks a guarantee its producer makes about the documents it emits.",
        _F.CANONICAL_VALIDITY,
    ),
    ReasonCode.RUN_BINDING_BROKEN: _spec(
        GateState.FAIL,
        "A canonical document names a different run than the one validated.",
        _F.PROVENANCE_LINKAGE,
    ),
    ReasonCode.LINKED_DOCUMENT_MISSING: _spec(
        GateState.FAIL,
        "A document the provenance chain runs through is missing, so the chain cannot be followed.",
        _F.PROVENANCE_LINKAGE,
    ),
    ReasonCode.SELECTION_BINDING_BROKEN: _spec(
        GateState.FAIL,
        "The sampling manifest is not bound to its site inventory, or a digest does not reproduce.",
        _F.PROVENANCE_LINKAGE,
    ),
    ReasonCode.ACQUISITION_LINKAGE_BROKEN: _spec(
        GateState.FAIL,
        "The page documents break a linkage guarantee: selection, record, measurement and "
        "evidence no longer resolve once and only once.",
        _F.PROVENANCE_LINKAGE,
    ),
    ReasonCode.DUPLICATE_IDENTIFIER: _spec(
        GateState.FAIL,
        "One identifier names two documents, so a reference to it is ambiguous.",
        _F.PROVENANCE_LINKAGE,
    ),
    ReasonCode.BUNDLE_FILE_MISSING: _spec(
        GateState.FAIL,
        "A canonical document is missing from the published artifact bundle.",
        _F.ARTIFACT_BUNDLE_VALIDITY,
    ),
    ReasonCode.BUNDLE_FILE_UNEXPECTED: _spec(
        GateState.FAIL,
        "The published artifact bundle contains a file that is not a canonical document of "
        "this run.",
        _F.ARTIFACT_BUNDLE_VALIDITY,
    ),
    ReasonCode.BUNDLE_FILE_NOT_JSON: _spec(
        GateState.FAIL,
        "A file of the published artifact bundle is not readable JSON.",
        _F.ARTIFACT_BUNDLE_VALIDITY,
    ),
    ReasonCode.BUNDLE_FILE_DIFFERS_FROM_CANONICAL: _spec(
        GateState.FAIL,
        "A file of the published artifact bundle differs from the canonical document it publishes.",
        _F.ARTIFACT_BUNDLE_VALIDITY,
    ),
    ReasonCode.VALIDATION_NOT_EVALUABLE: ReasonSpec(
        GateState.FAIL,
        _ALL_FAMILIES,
        "This gate could not be evaluated over the documents in hand; the defect is ours.",
    ),
    ReasonCode.RUN_FAILED_TECHNICALLY: _spec(
        GateState.BLOCKED,
        "The run ended without a selection because the target was refused or could not be "
        "reached. A process limitation, not a finding about the website.",
        _F.ACQUISITION_COMPLETENESS,
    ),
    ReasonCode.RUN_CANCELLED: _spec(
        GateState.BLOCKED,
        "The run was cancelled before it completed.",
        _F.ACQUISITION_COMPLETENESS,
    ),
    ReasonCode.SELECTION_INCOMPLETE: _spec(
        GateState.BLOCKED,
        "The sampling manifest states that the selection did not cover the site; its "
        "incompleteness cause names the bound of this analysis that stopped it.",
        _F.ACQUISITION_COMPLETENESS,
    ),
    ReasonCode.PAGE_NOT_ACQUIRED: _spec(
        GateState.BLOCKED,
        "A selected page was attempted but no response was received. A technical outcome, "
        "not a finding about the page.",
        _F.ACQUISITION_COMPLETENESS,
    ),
    ReasonCode.PAGE_BODY_TRUNCATED: _spec(
        GateState.BLOCKED,
        "A selected page's body was cut at this service's own byte bound.",
        _F.ACQUISITION_COMPLETENESS,
    ),
    ReasonCode.PAGE_BODY_NOT_DECODED: _spec(
        GateState.BLOCKED,
        "A selected page's body could not be decoded by this service.",
        _F.ACQUISITION_COMPLETENESS,
    ),
    ReasonCode.PAGE_MEASUREMENTS_WITHHELD: _spec(
        GateState.BLOCKED,
        "A page's measurements were withheld because its URL cannot be carried by the contracts.",
        _F.EVIDENCE_COVERAGE,
    ),
    ReasonCode.PAGE_EVIDENCE_NOT_ASSESSED: _spec(
        GateState.BLOCKED,
        "Some of a page's measurements were not assessed. Missing evidence, not negative evidence.",
        _F.EVIDENCE_COVERAGE,
    ),
    ReasonCode.PAGE_EVIDENCE_UNKNOWN: _spec(
        GateState.BLOCKED,
        "Some of a page's assessments established nothing (UNKNOWN). Missing evidence, not "
        "negative evidence.",
        _F.EVIDENCE_COVERAGE,
    ),
    ReasonCode.MEASUREMENT_WITHOUT_EVIDENCE: _spec(
        GateState.BLOCKED,
        "A measurement is named by no website evidence.",
        _F.EVIDENCE_COVERAGE,
    ),
    ReasonCode.UNRESOLVED_CONFLICT: _spec(
        GateState.BLOCKED,
        "An assessment reports a conflict that nothing has resolved.",
        _F.UNRESOLVED_CONFLICTS_LIMITATIONS,
    ),
    ReasonCode.DISCOVERY_SOURCE_LIMITED: _spec(
        GateState.BLOCKED,
        "A discovery source was cut short, refused, failed or could not be read, so the "
        "site inventory may not name every page.",
        _F.UNRESOLVED_CONFLICTS_LIMITATIONS,
    ),
    ReasonCode.RUN_EMITTED_NO_PAGE_DOCUMENTS: _spec(
        GateState.NOT_APPLICABLE,
        "The run did not succeed, so it emitted no page documents for this gate to evaluate; "
        "the acquisition completeness gate states why.",
        _F.EVIDENCE_COVERAGE,
        _F.UNRESOLVED_CONFLICTS_LIMITATIONS,
    ),
    ReasonCode.REQUEST_WITHHELD_BY_POLICY: _spec(
        GateState.NOT_APPLICABLE,
        "The target carried credentials, so the run refused it and, by data minimisation, "
        "persisted no request document; there is no input document to validate.",
        _F.INPUT_CONTRACT,
    ),
}


#: Every reason code as written, for membership tests on values read from a document. Only
#: strings are ever looked up in it: a document value of any other type is not a reason code.
_REASON_VALUES: Final[frozenset[str]] = frozenset(code.value for code in ReasonCode)


def reason_codes_with_effect(effect: GateState) -> list[str]:
    """The reason codes of one effect, in declaration order — the contract's enum for it."""
    return [code.value for code in ReasonCode if REASONS[code].effect is effect]


# --- building a gate ------------------------------------------------------------------------


def reason(code: ReasonCode, pointer: str | None = None, rule: str | None = None) -> dict[str, str]:
    """One reason document. ``pointer`` locates the subject; ``rule`` names the broken rule."""
    document: dict[str, str] = {"code": code.value}
    if pointer is not None:
        document["pointer"] = pointer
    if rule is not None:
        document["rule"] = rule
    return document


def _reason_key(item: Mapping[str, Any]) -> tuple[str, str, str]:
    return (str(item.get("code", "")), str(item.get("pointer", "")), str(item.get("rule", "")))


def ordered_reasons(reasons: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The reasons without repeats, ordered by ``(code, pointer, rule)``.

    The order is a function of the reasons alone, never of the order a validator happened to
    find them in, so one run validates to byte-identical gates every time.
    """
    unique = {_reason_key(item): dict(item) for item in reasons}
    return [unique[key] for key in sorted(unique)]


def gate_state_of(codes: Iterable[str]) -> GateState:
    """A gate's state, from the reasons it gives: none means it holds."""
    effects = {REASONS[ReasonCode(code)].effect for code in codes}
    if not effects:
        return GateState.PASS
    if GateState.FAIL in effects:
        return GateState.FAIL
    if GateState.BLOCKED in effects:
        return GateState.BLOCKED
    return GateState.NOT_APPLICABLE


def overall_state_of(states: Iterable[GateState]) -> GateState:
    """The run's validation state: ``FAIL > BLOCKED > PASS``, ``NOT_APPLICABLE`` neutral.

    Only applicable gates count. If none is applicable, nothing was established, and that is
    ``BLOCKED`` — never ``PASS``.
    """
    seen = set(states)
    if GateState.FAIL in seen:
        return GateState.FAIL
    if GateState.BLOCKED in seen:
        return GateState.BLOCKED
    if GateState.PASS in seen:
        return GateState.PASS
    return GateState.BLOCKED


def gate_document(reasons: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """One gate: its derived state and its ordered reasons."""
    ordered = ordered_reasons(reasons)
    return {
        "state": gate_state_of(item["code"] for item in ordered).value,
        "reasons": ordered,
    }


# --- what every receipt guarantees beyond its schema ---------------------------------------

#: ``rule name -> what a receipt guarantees``. JSON Schema states which tokens may appear and
#: which reason classes a gate state admits; these are the relationships it cannot state.
RECEIPT_RULES: Final[dict[str, str]] = {
    "every_gate_present": (
        "The receipt reports exactly the seven gate families, so a gate cannot be dropped to "
        "make a run look releasable."
    ),
    "reason_belongs_to_gate": (
        "Every reason is one its gate family may give, so a gate cannot borrow another's "
        "failure or exemption."
    ),
    "gate_state_follows_reasons": (
        "A gate's state is the state its reasons produce, so no gate is set by hand."
    ),
    "reasons_ordered_and_unique": (
        "A gate's reasons are unique and ordered by (code, pointer, rule), so one validation "
        "serialises to the same bytes every time."
    ),
    "overall_state_follows_gates": (
        "The overall state is FAIL > BLOCKED > PASS over the applicable gates."
    ),
    "pass_requires_succeeded_run": (
        "A validation passes only for a run that succeeded: a run that did not execute to the "
        "end has nothing to release."
    ),
}


def receipt_rule_violations(receipt: Any) -> tuple[SemanticViolation, ...]:
    """Every receipt rule the document breaks, or nothing. Never raises on a malformed one."""
    if not isinstance(receipt, dict) or not isinstance(receipt.get("gates"), dict):
        return (SemanticViolation("/gates", "every_gate_present"),)

    gates: dict[str, Any] = receipt["gates"]
    found: list[SemanticViolation] = []
    if set(gates) != {family.value for family in GateFamily}:
        found.append(SemanticViolation("/gates", "every_gate_present"))

    states: list[GateState] = []
    for family in GateFamily:
        gate = gates.get(family.value)
        at = f"/gates/{family.value}"
        if not isinstance(gate, dict) or not isinstance(gate.get("reasons"), list):
            continue
        reasons: list[Any] = gate["reasons"]
        codes: list[str] = []
        for index, item in enumerate(reasons):
            code = item.get("code") if isinstance(item, dict) else None
            if (
                not isinstance(code, str)
                or code not in _REASON_VALUES
                or family not in REASONS[ReasonCode(code)].families
            ):
                found.append(SemanticViolation(f"{at}/reasons/{index}", "reason_belongs_to_gate"))
            else:
                codes.append(code)
        if all(isinstance(item, dict) for item in reasons) and reasons != ordered_reasons(reasons):
            found.append(SemanticViolation(f"{at}/reasons", "reasons_ordered_and_unique"))
        if len(codes) == len(reasons):
            derived = gate_state_of(codes)
            if gate.get("state") != derived.value:
                found.append(SemanticViolation(f"{at}/state", "gate_state_follows_reasons"))
            states.append(derived)

    if len(states) == len(GateFamily):
        expected = overall_state_of(states)
        if receipt.get("overall_state") != expected.value:
            found.append(SemanticViolation("/overall_state", "overall_state_follows_gates"))
    if receipt.get("overall_state") == GateState.PASS.value and (
        receipt.get("run_state") != RunState.SUCCEEDED.value
    ):
        found.append(SemanticViolation("/overall_state", "pass_requires_succeeded_run"))
    return tuple(found)
