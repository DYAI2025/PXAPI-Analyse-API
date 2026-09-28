"""The vocabulary and the invariants of acquiring one *selected* page over static HTTP.

PXAPI-19 established which pages a site has. PXAPI-20 is the slice that may finally fetch the
ones a `sampling-manifest.v1` selected, and `page-acquisition-record.v1` is the record of one
such attempt. This module is that contract's domain side: the tokens it carries, the two values
a producer derives rather than observes, and the relationships a producer guarantees but JSON
Schema cannot state.

Four decisions live here, and each is a business decision rather than a transport detail.

**Which outcomes an attempt can have.** ``AcquisitionOutcome`` is a closed vocabulary because
every token has to name *our* side of the attempt — a response arrived, or one of the fetcher's
own refusal/failure kinds applied, or our runtime broke. None of them may describe the page. The
token set is deliberately ``RESPONSE_RECEIVED`` + every ``FetchFailureKind`` value + our own
``RUNTIME_ERROR``, spelled with the *same* strings, so a producer maps a failure with
``AcquisitionOutcome(failure.kind.value)`` and carries no translation table that could rot. The
Domain may not import a Port, so the equality is declared literally here and proved in
``tests/domain/test_page_acquisition.py``, which may import both.

**Which URLs a measurement can even be made against.** ``measurement-record.source_url`` and
``website-evidence.source_url`` reference ``common#/$defs/url``, and a selected page's canonical
identity references ``acquisition#/$defs/url_key``. Neither shape contains the other
(``C-PXAPI-020``): a 2048-character ``http`` URL with a 250-character authority is a valid
identity that ``common url`` refuses. A page whose identity or final URL cannot be carried
therefore yields **no** measurements and a stated reason, per page, rather than an invalid
document or a silent gap — which is what :func:`withheld_reason_for` decides and what the
contract's ``measurements_withheld_reason`` records. The shape is restated here because the
Domain may not import a validator, and it is pinned character for character against the schema.

**What the body digest is over.** The *decoded* bytes the fetcher returned, up to its own byte
bound — never the wire bytes and never anything about the URL. That is the only form in which
two runs over the same frozen response can be compared, and it is why the digest exists at all.

**What a producer guarantees.** The rules in :data:`PRODUCER_RULES` are not contract rules and
are never applied to a document somebody else wrote: they are what *this* producer promises
about the set of documents it emits together — that the records are the selections in rank
order, that each record binds the manifest it worked from, that one measurement belongs to one
page, that a page with no measurements says why. They fail **closed**:
:func:`require_emittable_acquisition` raises rather than returning a repaired set, because a
producer that patched its own output would be deciding what the analysis found.

**Which selection may be acquired at all.** PXAPI-20.B adds the admission gate that runs before
any fetch: :func:`admitted_page_refs` accepts the bound manifest only when it belongs to this
run, names and pins the inventory it was drawn from, reproduces its own digests, and selects
each Page Ref once from that inventory's eligible candidates. It fails closed with
:class:`SelectionNotAdmissible` and never admits part of a selection.

Standard library only. The domain ring imports no third-party distribution at all.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from enum import StrEnum
from typing import Any, Final

from pxapi.domain.acquisition_digests import (
    DIGEST_PREFIX,
    digest_of,
    inventory_output_projection,
    manifest_digests,
)
from pxapi.domain.acquisition_semantics import (
    ProducerInvariantViolated,
    SemanticViolation,
    manifest_producer_violations,
    sampling_manifest_violations,
)

#: The registered contract these rules are about.
PAGE_ACQUISITION_RECORD: Final = "page-acquisition-record"

#: How *this* producer observed the page. The contract's own vocabulary is wider — it carries the
#: two observation modes the accepted architecture defines, static and rendered — and this constant
#: is the one of them PXAPI-20 implements (D-20-C). The narrowing is enforced below, in
#: ``record_declares_this_producer``, which is why a rendered record can be a well-formed document
#: of that contract and still not be something this service may emit.
OBSERVATION_MODE_STATIC_HTTP: Final = "STATIC_HTTP"

#: Which method acquired it, and the version of that method. Together with the observation mode
#: these are the whole per-record provenance for a first-party static fetch: no third-party
#: provider is involved, so no provider member exists to name one (D-20-I). The exact
#: implementation SHA belongs in an execution receipt, not in every record.
ACQUISITION_METHOD: Final = "STATIC_HTTP_PAGE_FETCH"
ACQUISITION_METHOD_VERSION: Final = "1.0.0"

#: Why a page carries no measurements. One token, because there is exactly one reason this
#: producer withholds them: the page's own identity, or the URL the response came from, is not
#: representable as a contract ``url`` (C-PXAPI-020). It is never a statement about the page.
MEASUREMENTS_WITHHELD_SOURCE_URL: Final = "SOURCE_URL_NOT_REPRESENTABLE"

#: The HTTP status range a received response can carry. Both bounds are *derived*, not chosen:
#: ``http.client`` refuses a status line outside 100..999 with ``BadStatusLine``, so the fetcher
#: can never report one, and a narrower bound in the contract would make a real 6xx..9xx
#: response contract-invalid rather than merely unusual.
HTTP_STATUS_MIN: Final = 100
HTTP_STATUS_MAX: Final = 999

#: Where a set of acquisition records is addressed in a violation pointer. It is the envelope
#: member name the multi-page runtime carries them under, stated once so the producer, the
#: invariants and the evidence cannot disagree about it.
RECORDS_POINTER: Final = "/page_acquisitions"

#: The contract's own lexical shape for ``common#/$defs/url``, pattern and ``maxLength`` alike,
#: restated because the Domain may not import a validator or a file path, and pinned character
#: for character against the schema by ``tests/domain/test_page_acquisition.py`` — which also
#: checks the predicate against the reference validator itself, so agreement is measured rather
#: than assumed. The excluded set is built from escape *text*, so this file holds no raw control
#: character and the result is the schema's pattern text byte for byte.
_ESCAPE_TEXT: Final = "\\u"
_EXCLUDED: Final = (
    f"{_ESCAPE_TEXT}0000-{_ESCAPE_TEXT}0020{_ESCAPE_TEXT}007F-{_ESCAPE_TEXT}009F"
    f"{_ESCAPE_TEXT}2028{_ESCAPE_TEXT}2029"
)
COMMON_URL_PATTERN: Final = f"^https?://[^{_EXCLUDED}]{{1,2040}}(?!\\n)$"
MAX_CONTRACT_URL_LENGTH: Final = 2048

_COMMON_URL: Final[re.Pattern[str]] = re.compile(COMMON_URL_PATTERN)


class AcquisitionOutcome(StrEnum):
    """What became of one attempt to acquire one selected page.

    Every token names the transport or our own runtime. ``RESPONSE_RECEIVED`` says a response
    arrived and says nothing about its status: a 404 and a 503 are received responses whose
    status is a measurement, never a verdict. The seven middle tokens are the fetcher's own
    failure kinds, spelled identically so a producer needs no mapping table, and
    ``RUNTIME_ERROR`` is the one this module adds: the attempt raised inside our own code.
    """

    #: A response arrived. Its status, redirects and body facts are then carried by the record.
    RESPONSE_RECEIVED = "RESPONSE_RECEIVED"
    #: The target is not a permitted public destination. Refused before any socket was opened.
    BLOCKED_TARGET = "BLOCKED_TARGET"
    #: The hostname did not resolve.
    DNS_FAILURE = "DNS_FAILURE"
    #: The connection could not be established, or was lost.
    CONNECTION_FAILURE = "CONNECTION_FAILURE"
    #: A connect, read, or the overall deadline elapsed.
    TIMEOUT = "TIMEOUT"
    #: The redirect chain exceeded the configured bound.
    TOO_MANY_REDIRECTS = "TOO_MANY_REDIRECTS"
    #: A redirect response carried no usable Location, or one that is not a permitted target.
    INVALID_REDIRECT = "INVALID_REDIRECT"
    #: The peer spoke something we could not parse as HTTP, or the TLS handshake failed.
    PROTOCOL_ERROR = "PROTOCOL_ERROR"
    #: Our own code raised while acquiring this page. A statement about us, never about the page.
    RUNTIME_ERROR = "RUNTIME_ERROR"


def is_contract_url(value: Any) -> bool:
    """Whether ``value`` can be carried by a contract member of shape ``common#/$defs/url``.

    ``re.search`` rather than ``fullmatch``, because that is what the reference validator does
    with a ``pattern`` keyword and the pattern is anchored at both ends itself. A non-string is
    ``False`` rather than an error: the caller is deciding whether a value is representable, and
    "no" is the honest answer for a value that is not even a string.
    """
    return (
        isinstance(value, str)
        and len(value) <= MAX_CONTRACT_URL_LENGTH
        and _COMMON_URL.search(value) is not None
    )


def withheld_reason_for(url_key: str, final_url: str | None = None) -> str | None:
    """Why this page's measurements must be withheld, or ``None`` when they may be made.

    ``final_url`` is the URL a received response actually came from, or ``None`` when no
    response arrived. Both are checked, because the source-URL rule records some facts at the
    requested identity and the rest at the final URL: one unrepresentable value would make part
    of the page's records invalid, and a partly-published page is worse than a withheld one.
    """
    if not is_contract_url(url_key):
        return MEASUREMENTS_WITHHELD_SOURCE_URL
    if final_url is not None and not is_contract_url(final_url):
        return MEASUREMENTS_WITHHELD_SOURCE_URL
    return None


def body_digest(body: bytes) -> str:
    """The canonical digest of a decoded response body, with its algorithm carried in the value.

    Over those exact bytes and nothing else — not the wire bytes, which a content encoding may
    have changed, and not the URL they came from. The prefix comes from the digest producer this
    repository already has, so the written shape is stated in exactly one place.
    """
    return DIGEST_PREFIX + hashlib.sha256(body).hexdigest()


#: ``rule name -> what this producer guarantees``. The names are stable tokens, never free text:
#: an expectation that recorded a sentence would go red on a rewording, which is the same reason
#: the invalid-fixture expectations record schema keywords.
PRODUCER_RULES: Final[dict[str, str]] = {
    "one_record_per_selection": (
        "The emitted records are exactly the pages the bound manifest selected, one each, in "
        "selection-rank order — so acquisition completeness can be read off the set, and "
        "re-serialising the pages in another sequence is a different acquisition."
    ),
    "record_binds_manifest": (
        "Every record names the manifest it worked from, the exact selection it worked from, "
        "and the run it belongs to, so no record can be read against a population it did not "
        "see. The digest and not the manifest id is what pins the version."
    ),
    "record_declares_this_producer": (
        "Every record declares this producer's observation mode, method and method version, so "
        "a record made some other way cannot travel as though this producer had made it."
    ),
    "unique_acquisition_id": (
        "One acquisition identity belongs to one attempt, so a measurement that resolves to a "
        "record resolves to exactly one."
    ),
    "measurement_owned_once": (
        "One measurement belongs to one page. Two records naming the same measurement would "
        "make page identity ambiguous for every reader that follows the chain back."
    ),
    "every_measurement_is_owned": (
        "Every measurement this slice emitted is named by a record, so no page-scoped "
        "measurement exists whose page nobody can recover."
    ),
    "refs_name_a_measurement": (
        "Every measurement a record names was actually emitted, so the chain from evidence to "
        "page never runs through a reference that resolves nowhere."
    ),
    "refs_empty_iff_withheld": (
        "A record carries measurements, or it states why it carries none. A page with neither "
        "would be an unexplained gap a reader could attribute to the site."
    ),
    "evidence_within_one_page": (
        "Every evidence document derives from measurements of one page, so page identity "
        "survives to the one document type that may speak about the website."
    ),
    "no_polarity_on_page_evidence": (
        "No evidence this slice emits carries a polarity. Every fact it records is an "
        "observation, and PXAPI-20 emits no judgement about any page."
    ),
    "raw_artifact_ref_absent": (
        "No record points at a retained raw artifact, because this slice retains none. The "
        "member exists as future-facing provenance and is never emitted (D-20-H)."
    ),
}


def _selected_keys_in_rank_order(manifest: dict[str, Any]) -> list[Any] | None:
    """The manifest's selected identities ordered by rank, or ``None`` when rank is unusable.

    A rank that is absent, null or not a whole number is a structural defect the schema layer
    reports, and an order over it is undefined; ``sorted`` would raise on a list mixing ``None``
    with integers, and a checker that crashes reports nothing at all. ``bool`` is excluded
    because it is an ``int`` subclass in Python and ``True`` would otherwise pass for rank 1.
    """
    selections = manifest.get("selections")
    if not isinstance(selections, list):
        return None
    ranked = [
        item
        for item in selections
        if isinstance(item, dict)
        and isinstance(item.get("selection_rank"), int)
        and not isinstance(item.get("selection_rank"), bool)
    ]
    if len(ranked) != len(selections):
        return None
    return [item.get("url_key") for item in sorted(ranked, key=lambda item: item["selection_rank"])]


def acquisition_violations(
    records: Sequence[Any],
    manifest: dict[str, Any],
    measurements: Sequence[Any],
    evidence: Sequence[Any],
) -> tuple[SemanticViolation, ...]:
    """Every producer guarantee the emitted set of page documents must satisfy.

    The bound manifest is required rather than optional: half of these guarantees are about the
    relationship between the records and the selection they answer, and a check that silently
    skipped them when the manifest was not to hand would be an exemption nobody asked for.
    """
    found: list[SemanticViolation] = []

    expected = _selected_keys_in_rank_order(manifest)
    observed = [record.get("url_key") for record in records if isinstance(record, dict)]
    if expected is not None and observed != expected:
        found.append(SemanticViolation(RECORDS_POINTER, "one_record_per_selection"))

    known_measurements = {
        item["measurement_id"]
        for item in measurements
        if isinstance(item, dict) and isinstance(item.get("measurement_id"), str)
    }

    seen_acquisition_ids: list[Any] = []
    owner_of: dict[Any, int] = {}

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        at = f"{RECORDS_POINTER}/{index}"

        if (
            record.get("sampling_manifest_ref") != manifest.get("sampling_manifest_id")
            or record.get("sampling_manifest_output_digest") != manifest.get("output_digest")
            or record.get("run_id") != manifest.get("run_id")
        ):
            found.append(SemanticViolation(at, "record_binds_manifest"))

        if (
            record.get("observation_mode") != OBSERVATION_MODE_STATIC_HTTP
            or record.get("acquisition_method") != ACQUISITION_METHOD
            or record.get("acquisition_method_version") != ACQUISITION_METHOD_VERSION
        ):
            found.append(SemanticViolation(at, "record_declares_this_producer"))

        acquisition_id = record.get("acquisition_id")
        if acquisition_id in seen_acquisition_ids:
            found.append(SemanticViolation(at, "unique_acquisition_id"))
        else:
            seen_acquisition_ids.append(acquisition_id)

        if "raw_artifact_ref" in record:
            found.append(SemanticViolation(at, "raw_artifact_ref_absent"))

        refs = record.get("measurement_refs")
        if not isinstance(refs, list):
            continue

        if (not refs) != ("measurements_withheld_reason" in record):
            found.append(SemanticViolation(at, "refs_empty_iff_withheld"))

        unresolved = False
        for ref in refs:
            if ref not in known_measurements:
                unresolved = True
                continue
            if ref in owner_of:
                found.append(SemanticViolation(at, "measurement_owned_once"))
            else:
                owner_of[ref] = index
        if unresolved:
            found.append(SemanticViolation(at, "refs_name_a_measurement"))

    for index, item in enumerate(measurements):
        if isinstance(item, dict) and item.get("measurement_id") not in owner_of:
            found.append(SemanticViolation(f"/measurements/{index}", "every_measurement_is_owned"))

    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            continue
        at = f"/website_evidence/{index}"
        if "polarity" in item:
            found.append(SemanticViolation(at, "no_polarity_on_page_evidence"))
        refs = item.get("measurement_refs")
        if isinstance(refs, list) and refs:
            owners = {owner_of.get(ref) for ref in refs}
            if len(owners) != 1 or None in owners:
                found.append(SemanticViolation(at, "evidence_within_one_page"))

    return tuple(found)


def require_emittable_acquisition(
    records: Sequence[Any],
    manifest: dict[str, Any],
    measurements: Sequence[Any],
    evidence: Sequence[Any],
) -> None:
    """Fail closed on a set of page documents this producer may not emit.

    It raises the same exception the acquisition producer already raises for a document it must
    withhold, so one failure class covers "this service built something it may not publish"
    whatever contract it was building, and the offending documents are withheld rather than
    returned unvalidated.
    """
    found = acquisition_violations(records, manifest, measurements, evidence)
    if found:
        raise ProducerInvariantViolated(PAGE_ACQUISITION_RECORD, found)


# --- admission: which selection may be acquired at all ---------------------------------------

#: ``rule name -> what admission refuses``, checked over the bound manifest and inventory
#: *before* any page is fetched (D-20-B). A manifest that breaks one of these is not a selection
#: this runtime may act on: fetching it anyway would bind every record to a population that
#: cannot be resolved, and no outcome of those fetches could be read correctly afterwards. The
#: contract-semantic and producer rules of ``sampling-manifest.v1`` are applied as well, under
#: their own names, so an unknown Page Ref is reported as ``selection_is_an_inventory_candidate``
#: and a duplicated one as ``unique_selected_url_key`` rather than under a second spelling.
ADMISSION_RULES: Final[dict[str, str]] = {
    "manifest_binds_run": (
        "The manifest and the inventory belong to the run being executed, so no record of this "
        "run can answer a selection some other run planned."
    ),
    "manifest_binds_inventory": (
        "The manifest names the inventory it is bound to by identity and by exact output "
        "digest, so every selected Page Ref resolves against the population it was drawn from."
    ),
    "inventory_digest_reproduces": (
        "The inventory's output digest is the digest of its own content, so the binding above "
        "pins the population actually in hand rather than a claim about one."
    ),
    "manifest_digests_reproduce": (
        "The manifest's two digests are the digests of its own content, so the digest every "
        "acquisition record carries pins the selection that was actually acquired."
    ),
    "selection_present": (
        "The manifest carries at least one selection, each an object with a whole-number rank, "
        "so there is a deterministic order to acquire in."
    ),
}


class SelectionNotAdmissible(Exception):
    """The bound manifest and inventory do not form a selection this runtime may acquire.

    It names a defect in the documents this service produced and handed itself, never anything
    about the website, and it is raised before any page was fetched.
    """

    def __init__(self, violations: Sequence[SemanticViolation]) -> None:
        self.violations: tuple[SemanticViolation, ...] = tuple(violations)
        rendered = ", ".join(f"{v.pointer} [{v.rule}]" for v in self.violations)
        super().__init__(f"selection not admissible: {rendered}")

    @property
    def keys(self) -> set[tuple[str, str]]:
        return {violation.key for violation in self.violations}


def _reproduces(expected: Any, compute: Any) -> bool:
    """Whether ``compute()`` returns ``expected``; a document it cannot even digest does not.

    A projection raises on an ambiguous or structurally broken document, and that is exactly a
    document whose digest does not reproduce — the other admission rules then say why.
    """
    try:
        return bool(compute() == expected)
    except Exception:
        return False


def admission_violations(
    manifest: Any, inventory: Any, run_id: str
) -> tuple[SemanticViolation, ...]:
    """Every reason the bound manifest and inventory may not be acquired, or nothing."""
    if not isinstance(manifest, dict) or not isinstance(inventory, dict):
        return (SemanticViolation("", "manifest_binds_inventory"),)

    found: list[SemanticViolation] = []
    if manifest.get("run_id") != run_id or inventory.get("run_id") != run_id:
        found.append(SemanticViolation("/run_id", "manifest_binds_run"))

    names_inventory = manifest.get("inventory_ref") == inventory.get("inventory_id")
    pins_inventory = manifest.get("inventory_output_digest") == inventory.get("output_digest")
    if not (names_inventory and pins_inventory):
        found.append(SemanticViolation("/inventory_ref", "manifest_binds_inventory"))

    inventory_digest = inventory.get("output_digest")
    if not _reproduces(inventory_digest, lambda: digest_of(inventory_output_projection(inventory))):
        found.append(SemanticViolation("/inventory_output_digest", "inventory_digest_reproduces"))

    manifest_pair = (manifest.get("input_digest"), manifest.get("output_digest"))
    if not _reproduces(manifest_pair, lambda: manifest_digests(manifest)):
        found.append(SemanticViolation("/output_digest", "manifest_digests_reproduce"))

    selections = manifest.get("selections")
    if (
        not isinstance(selections, list)
        or not selections
        or _selected_keys_in_rank_order(manifest) is None
    ):
        found.append(SemanticViolation("/selections", "selection_present"))

    found += sampling_manifest_violations(manifest)
    found += manifest_producer_violations(manifest, inventory)
    return tuple(found)


def admitted_page_refs(manifest: Any, inventory: Any, run_id: str) -> tuple[str, ...]:
    """The selected Page Refs in rank order, or ``SelectionNotAdmissible`` before any fetch.

    Fails closed: the caller receives either the complete, unambiguous, resolvable selection or
    nothing at all. There is no partial admission, because acquiring the admissible half of a
    selection would silently omit the rest.
    """
    found = admission_violations(manifest, inventory, run_id)
    keys = _selected_keys_in_rank_order(manifest) if not found else None
    if keys is None:
        raise SelectionNotAdmissible(found)
    return tuple(keys)
