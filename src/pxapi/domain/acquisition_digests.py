"""The canonical serialisation and the four digest projections, as shipped producer behaviour.

D-PXAPI19-PO-004 fixes the digest topology of the two acquisition contracts: each carries
exactly an ``input_digest`` and an ``output_digest``, each is a canonical SHA-256 over a
deterministic UTF-8 JSON rendering with sorted keys and no floating-point member, envelope
identities and timestamps never participate, and the order in which a producer enumerated an
order-independent collection must not be able to change a value. PXAPI-19.A made that rule
executable as test code because it shipped no producer. This module is the producer.

The member classification below is the load-bearing part, and it is the same classification
19.A derived from the schemas: every root member of each contract belongs to exactly one of
four classes, so a member added later without a decision about whether it participates in a
digest is a change somebody has to make deliberately rather than one that happens quietly.

**Ambiguity is refused, not ordered.** Each projection sorts its order-independent collections
by their semantic keys. ``sorted`` is stable, so a document carrying a repeated key would be
left in the sequence it arrived in and its digest would silently become a function of that
sequence — different for two serialisations of the same document. The projections therefore run
the semantic gate first and raise rather than return a value that would only look canonical.

**What the input digest of an inventory covers** is the admitted discovery-observation input:
the accepted written form, the source that wrote it and, where the observation carried one, the
transient anchor label, for every observation that survived admission. The label never reaches
the document (D-PXAPI19-PO-007), but it can change a classification, so an input digest that
ignored it would let two different inputs claim one digest. It enters as bytes under a hash,
never as stored text, and a label-free record has exactly the 19.A reference shape.

Standard library only. The domain ring imports no third-party distribution at all.
"""

from __future__ import annotations

import hashlib
import json
from operator import itemgetter
from typing import Any, Final

from pxapi.domain.acquisition_semantics import (
    SAMPLING_MANIFEST,
    SITE_INVENTORY,
    require_unambiguous,
)

#: The canonical form: UTF-8, sorted keys, no insignificant whitespace, no non-JSON constant.
#: ``allow_nan=False`` is what makes the "no floating-point members" rule fail loudly rather
#: than emit ``NaN``, which is not JSON and which every numeric bound compares False against.
CANONICAL_JSON_OPTIONS: Final[dict[str, Any]] = {
    "sort_keys": True,
    "ensure_ascii": False,
    "separators": (",", ":"),
    "allow_nan": False,
}

#: The digest algorithm, carried in the value so a reader never has to assume one.
DIGEST_PREFIX: Final = "sha256:"

#: Identity and clock members: they exist so a document can be referenced and ordered, and they
#: never participate. Re-emitting the same population under a new id at a new instant must
#: leave both digests unchanged.
INVENTORY_ENVELOPE: Final[tuple[str, ...]] = (
    "schema_version",
    "run_id",
    "inventory_id",
    "generated_at",
)

#: The digest members themselves. A digest never digests itself or the other one.
INVENTORY_DIGESTS: Final[tuple[str, ...]] = ("input_digest", "output_digest")

#: Members the inventory's ``input_digest`` is computed over. Deliberately empty: the admitted
#: discovery observations are not carried by this document, so the input digest binds the
#: inventory to inputs held elsewhere. A decision of D-PXAPI19-PO-004, not an omission.
INVENTORY_INPUT: Final[tuple[str, ...]] = ()

#: The inventory's stable semantics, exactly as D-PXAPI19-PO-004 enumerates them.
INVENTORY_OUTPUT: Final[tuple[str, ...]] = (
    "target_origin",
    "discovery_method",
    "discovery_method_version",
    "classifier",
    "classifier_version",
    "sources",
    "candidates",
)

MANIFEST_ENVELOPE: Final[tuple[str, ...]] = (
    "schema_version",
    "run_id",
    "sampling_manifest_id",
    "generated_at",
)

MANIFEST_DIGESTS: Final[tuple[str, ...]] = ("input_digest", "output_digest")

#: What the selection was decided from: the bound inventory and the exact version of it, the
#: policy identity and version, and the declared decision-relevant budgets.
MANIFEST_INPUT: Final[tuple[str, ...]] = (
    "inventory_ref",
    "inventory_output_digest",
    "policy_id",
    "policy_version",
    "budgets",
)

#: The selection semantics. ``incompleteness`` belongs here rather than to the envelope because
#: it is part of what the selection *is*: two manifests that selected the same pages, one of
#: them cut off by a budget, are not the same selection and must not share an output digest.
MANIFEST_OUTPUT: Final[tuple[str, ...]] = (
    "mode",
    "selection_complete",
    "incompleteness",
    "selections",
    "exclusions",
)

#: ``contract -> {class name -> members}``. Read by the coverage test against the schemas, so a
#: member added later without a digest decision turns the suite red.
CLASSIFICATION: Final[dict[str, dict[str, tuple[str, ...]]]] = {
    SITE_INVENTORY: {
        "ENVELOPE": INVENTORY_ENVELOPE,
        "DIGEST": INVENTORY_DIGESTS,
        "INPUT": INVENTORY_INPUT,
        "OUTPUT": INVENTORY_OUTPUT,
    },
    SAMPLING_MANIFEST: {
        "ENVELOPE": MANIFEST_ENVELOPE,
        "DIGEST": MANIFEST_DIGESTS,
        "INPUT": MANIFEST_INPUT,
        "OUTPUT": MANIFEST_OUTPUT,
    },
}


def canonical_json(value: Any) -> bytes:
    """The deterministic UTF-8 JSON rendering a PXAPI digest is computed over."""
    return json.dumps(value, **CANONICAL_JSON_OPTIONS).encode("utf-8")


def digest_of(value: Any) -> str:
    """The canonical digest of ``value``, in the shape ``acquisition#/$defs/digest`` fixes."""
    return DIGEST_PREFIX + hashlib.sha256(canonical_json(value)).hexdigest()


def floats_in(value: Any, path: str = "") -> list[str]:
    """Every path at which ``value`` holds a floating-point number.

    ``bool`` is a subclass of ``int`` in Python and is deliberately not reported; a float is,
    because a digest over one is not portable across producers.
    """
    found: list[str] = []
    if isinstance(value, float):
        found.append(path or "/")
    elif isinstance(value, dict):
        for key, item in value.items():
            found.extend(floats_in(item, f"{path}/{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(floats_in(item, f"{path}/{index}"))
    return found


def _canonical_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """One candidate with its order-independent collections in canonical order.

    ``observed_forms`` and ``provenance`` are sets the contract renders as arrays. Digesting
    them as emitted would make the digest depend on the sequence in which a producer happened
    to visit sources — exactly the accident D-PXAPI19-PO-004 forbids.
    """
    return dict(
        candidate,
        observed_forms=sorted(candidate["observed_forms"]),
        provenance=sorted(candidate["provenance"]),
    )


def inventory_output_projection(document: dict[str, Any]) -> dict[str, Any]:
    """The inventory's stable semantics, with every order-independent collection sorted."""
    require_unambiguous(SITE_INVENTORY, document)
    projection = {member: document[member] for member in INVENTORY_OUTPUT}
    projection["sources"] = sorted(
        (dict(source) for source in document["sources"]), key=itemgetter("source_id")
    )
    projection["candidates"] = sorted(
        (_canonical_candidate(candidate) for candidate in document["candidates"]),
        key=itemgetter("url_key"),
    )
    return projection


def observation_input_projection(observations: list[dict[str, str]]) -> list[dict[str, str]]:
    """The admitted discovery observations in canonical order.

    Sorted rather than kept in the sequence it was handed, because that is the rule the
    inventory's ``input_digest`` declares: enumeration order cannot change the digest.
    """
    return sorted(
        (dict(observation) for observation in observations),
        key=lambda record: (record["observed_form"], record["source_id"], record.get("label", "")),
    )


def manifest_input_projection(document: dict[str, Any]) -> dict[str, Any]:
    """What the selection was decided from. ``budgets`` is omitted when none was declared."""
    return {member: document[member] for member in MANIFEST_INPUT if member in document}


def manifest_output_projection(document: dict[str, Any]) -> dict[str, Any]:
    """The selection semantics: selections in rank order, exclusions in canonical order.

    The ranks and not the array positions carry the order, so re-serialising the document with
    its selections in another sequence cannot change what the manifest means. Exclusions are a
    per-reason summary and carry no order at all, so they are sorted. ``incompleteness``
    participates and is omitted when the selection ran to its end, because the contract admits
    it only alongside ``selection_complete: false`` and projecting an absent member would
    invent one.
    """
    require_unambiguous(SAMPLING_MANIFEST, document)
    projection = {member: document[member] for member in ("mode", "selection_complete")}
    if "incompleteness" in document:
        projection["incompleteness"] = dict(document["incompleteness"])
    projection["selections"] = [
        dict(selection)
        for selection in sorted(document["selections"], key=itemgetter("selection_rank"))
    ]
    projection["exclusions"] = sorted(
        (dict(exclusion) for exclusion in document["exclusions"]), key=itemgetter("reason")
    )
    return projection


def inventory_digests(
    document: dict[str, Any], observations: list[dict[str, str]]
) -> tuple[str, str]:
    """``(input_digest, output_digest)`` for one inventory and the observations behind it."""
    return (
        digest_of(observation_input_projection(observations)),
        digest_of(inventory_output_projection(document)),
    )


def manifest_digests(document: dict[str, Any]) -> tuple[str, str]:
    """``(input_digest, output_digest)`` for one sampling manifest."""
    return (
        digest_of(manifest_input_projection(document)),
        digest_of(manifest_output_projection(document)),
    )
