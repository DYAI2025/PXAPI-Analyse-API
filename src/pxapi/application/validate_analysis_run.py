"""Validating one completed multi-page Analysis Run into an ``analysis-validation-receipt.v1``.

PXAPI-25 separates two questions the run state used to leave merged. ``SUCCEEDED`` says the run
*executed*; this use case says whether its result can be *relied on*, gate by gate, with the
exact reason for every gate that does not hold. It reads the canonical documents a run produced
and the artifact bundle published from them, and it changes neither: Validation never changes
Analysis Truth, and the receipt it returns is a statement about the run, never a member of it.

**The gates are evaluated over what was produced, never over what a producer promised.** Every
document is checked against its registered contract through the ``ContractValidation`` port, the
contract-semantic and producer rules are applied through the Domain functions that already state
them, and the bundle is compared byte for byte with the canonical serialisation of the documents
it publishes. Nothing here restates a contract shape or a linkage rule.

**No circularity.** ``ARTIFACT_BUNDLE_VALIDITY`` validates the canonical bundle; the receipt is
built afterwards, carries the bundle's digest, and is never part of the input it decides. A
bundle that already contains a receipt is therefore not this run's canonical bundle.

**Neutrality.** A technical outcome — an incomplete selection, a timeout, a refused target, an
undecodable body, an assessment that was not made — is a ``BLOCKED`` reason about our process.
None of them is a ``FAIL``, which is reserved for defects of this service, and none of them is a
statement about the website.

The layer holds no transport, no validator and no clock of its own: it is handed a
``ContractValidation``, a clock and an id factory, which is what lets one frozen input validate
to byte-identical receipts on every run.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from pxapi.application.acquire_selected_pages import (
    ACQUISITION_WITHHELD_CODE,
    SELECTION_NOT_ADMISSIBLE_CODE,
)
from pxapi.application.discover_site import (
    BOOTSTRAP_FAILURE_CODE,
    INVENTORY_WITHHELD_CODE,
    MANIFEST_WITHHELD_CODE,
    UNEXPLAINED_BOOTSTRAP_CODE,
)
from pxapi.domain.acquisition_digests import DIGEST_PREFIX, digest_of
from pxapi.domain.acquisition_semantics import (
    CONTRACT_RULES,
    SAMPLING_MANIFEST,
    SITE_INVENTORY,
    violations_of,
)
from pxapi.domain.page_acquisition import (
    AcquisitionOutcome,
    acquisition_violations,
    admission_violations,
)
from pxapi.domain.run_state import RunState
from pxapi.domain.run_validation import (
    GateFamily,
    GateState,
    ReasonCode,
    gate_document,
    overall_state_of,
    reason,
)
from pxapi.domain.site_discovery import SourceOutcome
from pxapi.ports.contract_validation import ContractValidation

#: The contract this use case produces, and the file its document is published as.
RECEIPT_CONTRACT: Final = "analysis-validation-receipt"
RECEIPT_FILE: Final = "analysis-validation-receipt.json"

#: Who validated, and by which version of the method. Two receipts are comparable only when the
#: validator and its version agree, so both are recorded rather than assumed.
VALIDATOR: Final = "ANALYSIS_RUN_VALIDATOR"
VALIDATOR_VERSION: Final = "1.0.0"


@dataclass(frozen=True)
class CanonicalMember:
    """One canonical envelope member: its contract, its bundle file, and its container."""

    contract: str
    file_name: str
    plural: bool


#: ``envelope member -> contract, bundle file, container``. The same fact the multi-page command
#: line states as ``PRODUCED_DOCUMENTS`` and ``CONTAINER_SHAPES``; the application layer may not
#: import an adapter, so it is declared here and pinned against that adapter by
#: ``tests/application/test_validate_analysis_run.py``.
CANONICAL_MEMBERS: Final[dict[str, CanonicalMember]] = {
    "analysis_run_request": CanonicalMember(
        "analysis-run-request", "analysis-run-request.json", plural=False
    ),
    "analysis_run_state": CanonicalMember(
        "analysis-run-state", "analysis-run-state.json", plural=False
    ),
    "stage_executions": CanonicalMember(
        "stage-execution-record", "stage-execution-records.json", plural=True
    ),
    "site_inventory": CanonicalMember("site-inventory", "site-inventory.json", plural=False),
    "sampling_manifest": CanonicalMember(
        "sampling-manifest", "sampling-manifest.json", plural=False
    ),
    "page_acquisitions": CanonicalMember(
        "page-acquisition-record", "page-acquisition-records.json", plural=True
    ),
    "measurements": CanonicalMember("measurement-record", "measurement-records.json", plural=True),
    "website_evidence": CanonicalMember("website-evidence", "website-evidence.json", plural=True),
}

#: The members every run carries, whatever became of it.
ALWAYS_EMITTED: Final[tuple[str, ...]] = (
    "analysis_run_request",
    "analysis_run_state",
    "stage_executions",
)

#: The members only a succeeded run carries in full: the population and the page documents.
PAGE_MEMBERS: Final[tuple[str, ...]] = ("page_acquisitions", "measurements", "website_evidence")

#: A run that failed on our own side of the boundary before a selection existed: the target was
#: refused, could not be reached, or discovery failed technically. Derived from the producers'
#: own code tables, never restated. BLOCKED, never FAIL: none of them is a defect we emitted.
TECHNICAL_RUN_FAILURES: Final[frozenset[str]] = frozenset(
    {*BOOTSTRAP_FAILURE_CODE.values(), UNEXPLAINED_BOOTSTRAP_CODE}
)

#: A run that failed because this service built a document it may not emit. FAIL.
PRODUCER_DEFECT_RUN_FAILURES: Final[frozenset[str]] = frozenset(
    {
        INVENTORY_WITHHELD_CODE,
        MANIFEST_WITHHELD_CODE,
        SELECTION_NOT_ADMISSIBLE_CODE,
        ACQUISITION_WITHHELD_CODE,
    }
)

#: Discovery source outcomes under which the inventory may not name every page: the source was
#: cut short by our bound or our clock, refused by our policy, failed in a provider or in our
#: runtime, or could not be parsed. ``USED``, ``EMPTY``, ``ABSENT`` and
#: ``NO_SITEMAP_DECLARATION`` are facts that limit nothing.
LIMITING_SOURCE_OUTCOMES: Final[frozenset[str]] = frozenset(
    {
        SourceOutcome.BUDGET_EXHAUSTED.value,
        SourceOutcome.TARGET_POLICY_REFUSED.value,
        SourceOutcome.PROVIDER_FAILURE.value,
        SourceOutcome.RUNTIME_ERROR.value,
        SourceOutcome.TIMEOUT.value,
        SourceOutcome.MALFORMED.value,
    }
)

#: The bound on a reason pointer, as the contract's ``json_pointer`` definition states it, and the
#: two Unicode separators its pattern refuses besides the C0 and C1 controls.
_MAX_POINTER_LENGTH: Final = 512
_SEPARATORS: Final = (chr(0x2028), chr(0x2029))


def canonical_bytes(value: Any) -> bytes:
    """The one serialisation a canonical document is published in.

    Byte-identical to the multi-page command line's artifact files, so a bundle published by
    either entry point reads back the same way; ``tests/application/`` pins the equality.
    """
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def build_artifact_bundle(envelope: Mapping[str, Any]) -> dict[str, bytes]:
    """``file name -> bytes`` for exactly the canonical documents this run emitted.

    The receipt is deliberately absent: it is produced *from* this bundle, so it cannot be a
    member of the bundle it validates.
    """
    return {
        member.file_name: canonical_bytes(envelope[name])
        for name, member in CANONICAL_MEMBERS.items()
        if name in envelope
    }


def bundle_digest(bundle: Mapping[str, bytes]) -> str:
    """The digest of a bundle: over each file's name and the SHA-256 of its exact bytes."""
    return digest_of(
        {
            name: DIGEST_PREFIX + hashlib.sha256(content).hexdigest()
            for name, content in bundle.items()
        }
    )


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _pointer(*parts: Any) -> str:
    return "".join(f"/{_escape(str(part))}" for part in parts)


def _within(base: str, relative: str) -> str:
    """``relative`` below ``base``, or ``base`` alone when the result is not a carriable pointer.

    Reason pointers are structural and bounded by the contract; a pointer this validator cannot
    carry falls back to the member it lies in rather than being truncated into a false address.
    """
    joined = base + relative
    if len(joined) > _MAX_POINTER_LENGTH or any(
        ord(char) < 0x20 or 0x7F <= ord(char) <= 0x9F or char in _SEPARATORS for char in joined
    ):
        return base
    return joined


def _strict_json(raw: bytes) -> Any:
    def refuse(token: str) -> Any:
        raise ValueError(f"non-JSON constant {token}")

    return json.loads(raw.decode("utf-8"), parse_constant=refuse)


def _dicts(value: Any) -> list[dict[str, Any]] | None:
    """``value`` as a list of objects, or ``None`` when it is not exactly that."""
    if isinstance(value, list) and all(isinstance(item, dict) for item in value):
        return value
    return None


def _documents(member: CanonicalMember, value: Any) -> list[dict[str, Any]] | None:
    """A member's documents, or ``None`` when its container is not the published shape."""
    if member.plural:
        return _dicts(value)
    return [value] if isinstance(value, dict) else None


def _state(envelope: Mapping[str, Any]) -> str | None:
    state = envelope.get("analysis_run_state")
    value = state.get("state") if isinstance(state, dict) else None
    return value if isinstance(value, str) else None


Reasons = Iterator[dict[str, str]]


class ValidateAnalysisRun:
    """Turns one completed run and its published bundle into a validation receipt."""

    def __init__(
        self,
        contracts: ContractValidation,
        clock: Callable[[], datetime],
        new_id: Callable[[], str],
    ) -> None:
        self.contracts = contracts
        self.clock = clock
        self.new_id = new_id

    # --- the use case ------------------------------------------------------------------

    def run(
        self,
        envelope: Mapping[str, Any],
        bundle: Mapping[str, bytes],
        *,
        run_id: str,
        declared_budget: int,
    ) -> dict[str, Any]:
        """Validate one run. ``run_id`` and ``declared_budget`` are what the caller submitted.

        They are handed in rather than read out of the envelope, because the question is
        whether the documents belong to the run that was requested under the budget that was
        declared — reading both from the documents under test would let them vouch for
        themselves.
        """
        if isinstance(declared_budget, bool) or not isinstance(declared_budget, int):
            raise ValueError("declared_budget must be a whole number")
        if declared_budget < 1:
            raise ValueError("declared_budget must be at least 1")

        evaluations: dict[GateFamily, Callable[[], Reasons]] = {
            GateFamily.INPUT_CONTRACT: lambda: self._input_contract(
                envelope, run_id, declared_budget
            ),
            GateFamily.ACQUISITION_COMPLETENESS: lambda: self._acquisition_completeness(envelope),
            GateFamily.CANONICAL_VALIDITY: lambda: self._canonical_validity(envelope),
            GateFamily.PROVENANCE_LINKAGE: lambda: self._provenance_linkage(envelope, run_id),
            GateFamily.EVIDENCE_COVERAGE: lambda: self._evidence_coverage(envelope),
            GateFamily.UNRESOLVED_CONFLICTS_LIMITATIONS: lambda: self._conflicts_limitations(
                envelope
            ),
            GateFamily.ARTIFACT_BUNDLE_VALIDITY: lambda: self._bundle_validity(envelope, bundle),
        }
        gates = {
            family.value: gate_document(_evaluated(evaluations[family])) for family in GateFamily
        }

        receipt: dict[str, Any] = {
            "schema_version": "1.0.0",
            "receipt_id": self.new_id(),
            "run_id": run_id,
            "validated_at": self.clock().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "validator": VALIDATOR,
            "validator_version": VALIDATOR_VERSION,
        }
        state = _state(envelope)
        if state in {value.value for value in RunState}:
            receipt["run_state"] = state
        receipt["artifact_bundle_digest"] = bundle_digest(bundle)
        receipt["overall_state"] = overall_state_of(
            _state_of(gate) for gate in gates.values()
        ).value
        receipt["gates"] = gates
        return receipt

    # --- INPUT_CONTRACT ----------------------------------------------------------------

    def _input_contract(
        self, envelope: Mapping[str, Any], run_id: str, declared_budget: int
    ) -> Reasons:
        request = envelope.get("analysis_run_request")
        if not isinstance(request, dict):
            yield reason(ReasonCode.REQUEST_MISSING, "/analysis_run_request")
        else:
            for violation in self.contracts.validate("analysis-run-request", request):
                yield reason(
                    ReasonCode.REQUEST_CONTRACT_INVALID,
                    _within("/analysis_run_request", violation.pointer),
                    violation.keyword,
                )
            if request.get("run_id") != run_id:
                yield reason(ReasonCode.REQUEST_NOT_BOUND_TO_RUN, "/analysis_run_request/run_id")

        manifest = envelope.get("sampling_manifest")
        if isinstance(manifest, dict):
            budgets = manifest.get("budgets")
            declared = budgets.get("max_selected_pages") if isinstance(budgets, dict) else None
            if isinstance(declared, bool) or declared != declared_budget:
                yield reason(ReasonCode.DECLARED_BUDGET_NOT_APPLIED, "/sampling_manifest/budgets")

    # --- ACQUISITION_COMPLETENESS ------------------------------------------------------

    def _acquisition_completeness(self, envelope: Mapping[str, Any]) -> Reasons:
        state = _state(envelope)
        if state is None:
            yield reason(ReasonCode.RUN_STATE_UNAVAILABLE, "/analysis_run_state")
            return
        if state == RunState.FAILED.value:
            failure = envelope["analysis_run_state"].get("failure")
            code = failure.get("code") if isinstance(failure, dict) else None
            at = "/analysis_run_state/failure/code"
            if code in TECHNICAL_RUN_FAILURES:
                yield reason(ReasonCode.RUN_FAILED_TECHNICALLY, at)
            elif code in PRODUCER_DEFECT_RUN_FAILURES:
                yield reason(ReasonCode.RUN_FAILED_BY_PRODUCER_DEFECT, at)
            else:
                yield reason(ReasonCode.RUN_FAILURE_UNCLASSIFIED, at)
            return
        if state == RunState.CANCELLED.value:
            yield reason(ReasonCode.RUN_CANCELLED, "/analysis_run_state/state")
            return
        if state != RunState.SUCCEEDED.value:
            yield reason(ReasonCode.RUN_NOT_TERMINAL, "/analysis_run_state/state")
            return

        manifest = envelope.get("sampling_manifest")
        records = _dicts(envelope.get("page_acquisitions"))
        if not isinstance(manifest, dict) or records is None:
            yield reason(ReasonCode.ACQUISITION_RECORDS_MISSING, "/page_acquisitions")
            return
        if manifest.get("selection_complete") is not True:
            yield reason(ReasonCode.SELECTION_INCOMPLETE, "/sampling_manifest/selection_complete")
        for index, record in enumerate(records):
            if record.get("acquisition_outcome") != AcquisitionOutcome.RESPONSE_RECEIVED.value:
                yield reason(
                    ReasonCode.PAGE_NOT_ACQUIRED,
                    _pointer("page_acquisitions", index, "acquisition_outcome"),
                )
                continue
            if record.get("body_truncated") is not False:
                yield reason(
                    ReasonCode.PAGE_BODY_TRUNCATED,
                    _pointer("page_acquisitions", index, "body_truncated"),
                )
            if record.get("body_decoded") is not True:
                yield reason(
                    ReasonCode.PAGE_BODY_NOT_DECODED,
                    _pointer("page_acquisitions", index, "body_decoded"),
                )

    # --- CANONICAL_VALIDITY ------------------------------------------------------------

    def _canonical_validity(self, envelope: Mapping[str, Any]) -> Reasons:
        required = (
            tuple(CANONICAL_MEMBERS)
            if _state(envelope) == RunState.SUCCEEDED.value
            else ALWAYS_EMITTED
        )
        valid: dict[str, dict[str, Any]] = {}
        for name, member in CANONICAL_MEMBERS.items():
            if name not in envelope:
                if name in required:
                    yield reason(ReasonCode.CANONICAL_MEMBER_MISSING, _pointer(name))
                continue
            value = envelope[name]
            documents = (
                _dicts(value) if member.plural else ([value] if isinstance(value, dict) else None)
            )
            if documents is None:
                yield reason(ReasonCode.DOCUMENT_CONTAINER_INVALID, _pointer(name))
                continue
            broken = False
            for index, document in enumerate(documents):
                base = _pointer(name, index) if member.plural else _pointer(name)
                for violation in self.contracts.validate(member.contract, document):
                    broken = True
                    yield reason(
                        ReasonCode.DOCUMENT_CONTRACT_INVALID,
                        _within(base, violation.pointer),
                        violation.keyword,
                    )
            if not broken and not member.plural:
                valid[name] = value

        for name in envelope:
            if name not in CANONICAL_MEMBERS:
                yield reason(ReasonCode.CANONICAL_MEMBER_UNEXPECTED, _pointer(name))

        # The contract-semantic rules JSON Schema cannot state, applied only to a document that
        # already satisfies its contract: over a structurally broken one they are undefined.
        for name, contract in (
            ("site_inventory", SITE_INVENTORY),
            ("sampling_manifest", SAMPLING_MANIFEST),
        ):
            if name in valid:
                for violation in violations_of(contract, valid[name]):
                    yield reason(
                        ReasonCode.DOCUMENT_SEMANTICS_INVALID,
                        _within(_pointer(name), violation.pointer),
                        violation.rule,
                    )

    # --- PROVENANCE_LINKAGE ------------------------------------------------------------

    def _provenance_linkage(self, envelope: Mapping[str, Any], run_id: str) -> Reasons:
        for name, member in CANONICAL_MEMBERS.items():
            value = envelope.get(name)
            documents = (
                _dicts(value) if member.plural else ([value] if isinstance(value, dict) else None)
            )
            for index, document in enumerate(documents or []):
                if document.get("run_id") != run_id:
                    at = (
                        _pointer(name, index, "run_id")
                        if member.plural
                        else _pointer(name, "run_id")
                    )
                    yield reason(ReasonCode.RUN_BINDING_BROKEN, at)

        if _state(envelope) != RunState.SUCCEEDED.value:
            return

        inventory = envelope.get("site_inventory")
        manifest = envelope.get("sampling_manifest")
        pages = {name: _dicts(envelope.get(name)) for name in PAGE_MEMBERS}
        missing = [
            name
            for name, present in (
                ("site_inventory", isinstance(inventory, dict)),
                ("sampling_manifest", isinstance(manifest, dict)),
                *((name, pages[name] is not None) for name in PAGE_MEMBERS),
            )
            if not present
        ]
        for name in missing:
            yield reason(ReasonCode.LINKED_DOCUMENT_MISSING, _pointer(name))
        if missing:
            return
        assert isinstance(manifest, dict)  # narrowed by ``missing`` above

        # Which selection the pages answer, and whether it is the one the inventory pins. The
        # contract-semantic rules among these are reported by CANONICAL_VALIDITY already.
        for violation in admission_violations(manifest, inventory, run_id):
            if violation.rule not in CONTRACT_RULES:
                yield reason(
                    ReasonCode.SELECTION_BINDING_BROKEN,
                    _within("/sampling_manifest", violation.pointer),
                    violation.rule,
                )

        records = pages["page_acquisitions"] or []
        measurements = pages["measurements"] or []
        evidence = pages["website_evidence"] or []
        for violation in acquisition_violations(records, manifest, measurements, evidence):
            yield reason(ReasonCode.ACQUISITION_LINKAGE_BROKEN, violation.pointer, violation.rule)

        for name, key in (("measurements", "measurement_id"), ("website_evidence", "evidence_id")):
            seen: set[Any] = set()
            for index, document in enumerate(pages[name] or []):
                identity = document.get(key)
                if not isinstance(identity, str):
                    continue
                if identity in seen:
                    yield reason(ReasonCode.DUPLICATE_IDENTIFIER, _pointer(name, index, key))
                seen.add(identity)

    # --- EVIDENCE_COVERAGE ---------------------------------------------------------------

    def _evidence_coverage(self, envelope: Mapping[str, Any]) -> Reasons:
        if _state(envelope) != RunState.SUCCEEDED.value:
            yield reason(ReasonCode.RUN_EMITTED_NO_PAGE_DOCUMENTS)
            return
        pages = {name: _dicts(envelope.get(name)) for name in PAGE_MEMBERS}
        for name, documents in pages.items():
            if documents is None:
                yield reason(ReasonCode.VALIDATION_NOT_EVALUABLE, _pointer(name))
        if any(documents is None for documents in pages.values()):
            return

        records = pages["page_acquisitions"] or []
        measurements = pages["measurements"] or []
        evidence = pages["website_evidence"] or []
        by_id = {
            item["measurement_id"]: item
            for item in measurements
            if isinstance(item.get("measurement_id"), str)
        }
        evidenced = {
            ref
            for item in evidence
            for ref in (item.get("measurement_refs") or [])
            if isinstance(ref, str)
        }

        for index, record in enumerate(records):
            at = _pointer("page_acquisitions", index)
            if "measurements_withheld_reason" in record:
                yield reason(ReasonCode.PAGE_MEASUREMENTS_WITHHELD, at)
            refs = record.get("measurement_refs")
            owned = [by_id[ref] for ref in refs if ref in by_id] if isinstance(refs, list) else []
            assessments = [item.get("assessment") for item in owned]
            assessments = [item for item in assessments if isinstance(item, dict)]
            if any("not_assessed_reason" in item for item in assessments):
                yield reason(ReasonCode.PAGE_EVIDENCE_NOT_ASSESSED, at)
            if any(item.get("result_state") == "UNKNOWN" for item in assessments):
                yield reason(ReasonCode.PAGE_EVIDENCE_UNKNOWN, at)

        for index, item in enumerate(measurements):
            if item.get("measurement_id") not in evidenced:
                yield reason(
                    ReasonCode.MEASUREMENT_WITHOUT_EVIDENCE, _pointer("measurements", index)
                )

    # --- UNRESOLVED_CONFLICTS_LIMITATIONS -----------------------------------------------

    def _conflicts_limitations(self, envelope: Mapping[str, Any]) -> Reasons:
        if _state(envelope) != RunState.SUCCEEDED.value:
            yield reason(ReasonCode.RUN_EMITTED_NO_PAGE_DOCUMENTS)
            return
        for name in ("measurements", "website_evidence"):
            documents = _dicts(envelope.get(name))
            if documents is None:
                yield reason(ReasonCode.VALIDATION_NOT_EVALUABLE, _pointer(name))
                continue
            for index, document in enumerate(documents):
                assessment = document.get("assessment")
                if isinstance(assessment, dict) and assessment.get("result_state") == "CONFLICT":
                    yield reason(
                        ReasonCode.UNRESOLVED_CONFLICT,
                        _pointer(name, index, "assessment", "result_state"),
                    )

        inventory = envelope.get("site_inventory")
        sources = _dicts(inventory.get("sources")) if isinstance(inventory, dict) else None
        if sources is None:
            yield reason(ReasonCode.VALIDATION_NOT_EVALUABLE, "/site_inventory")
            return
        for index, source in enumerate(sources):
            if source.get("outcome") in LIMITING_SOURCE_OUTCOMES:
                yield reason(
                    ReasonCode.DISCOVERY_SOURCE_LIMITED,
                    _pointer("site_inventory", "sources", index, "outcome"),
                )

    # --- ARTIFACT_BUNDLE_VALIDITY --------------------------------------------------------

    def _bundle_validity(self, envelope: Mapping[str, Any], bundle: Mapping[str, bytes]) -> Reasons:
        expected = build_artifact_bundle(envelope)
        for name in sorted(set(bundle) - set(expected)):
            yield reason(ReasonCode.BUNDLE_FILE_UNEXPECTED, _within("", _pointer(name)))
        for name, content in expected.items():
            at = _pointer(name)
            if name not in bundle:
                yield reason(ReasonCode.BUNDLE_FILE_MISSING, at)
                continue
            published = bundle[name]
            try:
                _strict_json(published)
            except (UnicodeDecodeError, ValueError):
                yield reason(ReasonCode.BUNDLE_FILE_NOT_JSON, at)
                continue
            if published != content:
                yield reason(ReasonCode.BUNDLE_FILE_DIFFERS_FROM_CANONICAL, at)


def _evaluated(evaluate: Callable[[], Reasons]) -> list[dict[str, str]]:
    """Every reason one gate gives, or ``VALIDATION_NOT_EVALUABLE`` if evaluating it raised.

    A gate that crashes over documents it cannot read fails closed: it reports that it could
    not be evaluated rather than reporting the reasons it found before it stopped, which would
    read as a complete evaluation.
    """
    try:
        return list(evaluate())
    except Exception:
        return [reason(ReasonCode.VALIDATION_NOT_EVALUABLE)]


def _state_of(gate: Mapping[str, Any]) -> GateState:
    return GateState(gate["state"])
