"""The canonical serialisation and the declared digest projections, as test code.

PXAPI-19.A ships contracts and no producer, so nothing under ``src/`` computes a digest. What
can still be proved without a producer is the *rule*: which members of each contract a digest
is computed over, that the serialisation is deterministic, that an order-independent collection
cannot make a digest order-dependent, and that an envelope identity or timestamp never
participates. This module is the reference implementation of that rule, and it lives in the
tests because it is a statement about the contracts rather than shipped behaviour.

The member classification below is the load-bearing part. Every root member of each of the two
contracts belongs to exactly one class, and ``test_digest_semantics`` derives the class
coverage from the schemas themselves — so a member added later without a decision about whether
it participates in a digest turns the suite red instead of silently digesting or silently
escaping.
"""

from __future__ import annotations

import hashlib
import json
from operator import itemgetter
from typing import Any

from tests.acquisition.semantics import (
    SAMPLING_MANIFEST,
    SITE_INVENTORY,
    require_unambiguous,
)

#: The canonical form: UTF-8, sorted keys, no insignificant whitespace, and no non-JSON
#: constant. ``allow_nan=False`` is what makes the "no floating-point members" rule fail loudly
#: rather than emit ``NaN``, which is not JSON and which every numeric bound compares False
#: against.
CANONICAL_JSON_OPTIONS: dict[str, Any] = {
    "sort_keys": True,
    "ensure_ascii": False,
    "separators": (",", ":"),
    "allow_nan": False,
}

#: The digest algorithm, carried in the value so a reader never has to assume one.
DIGEST_PREFIX = "sha256:"


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


# --- the member classification ---------------------------------------------------------------

#: ``SITE_INVENTORY`` and ``SAMPLING_MANIFEST`` are imported from ``tests.acquisition.semantics``
#: rather than restated here, so the fail-closed gate and the classification it guards cannot end
#: up naming different contracts. Modules that import them from this one keep working unchanged.

#: Identity and clock members. They exist so a document can be referenced and ordered, and they
#: never participate in a digest: re-emitting the same population under a new id at a new
#: instant must leave both digests unchanged.
INVENTORY_ENVELOPE: tuple[str, ...] = (
    "schema_version",
    "run_id",
    "inventory_id",
    "generated_at",
)

#: The digest members themselves. A digest never digests itself or the other one.
INVENTORY_DIGESTS: tuple[str, ...] = ("input_digest", "output_digest")

#: Members the inventory's ``input_digest`` is computed over. Deliberately empty: the admitted
#: discovery observations are not carried by this document, so the input digest binds the
#: inventory to inputs held elsewhere. That is a decision of D-PXAPI19-PO-004, not an omission.
INVENTORY_INPUT: tuple[str, ...] = ()

#: The inventory's stable semantics, exactly as D-PXAPI19-PO-004 enumerates them: target and
#: canonical origin, discovery method and version, classifier and version, source outcomes and
#: normalised candidates.
INVENTORY_OUTPUT: tuple[str, ...] = (
    "target_origin",
    "discovery_method",
    "discovery_method_version",
    "classifier",
    "classifier_version",
    "sources",
    "candidates",
)

MANIFEST_ENVELOPE: tuple[str, ...] = (
    "schema_version",
    "run_id",
    "sampling_manifest_id",
    "generated_at",
)

MANIFEST_DIGESTS: tuple[str, ...] = ("input_digest", "output_digest")

#: What the selection was decided from: the bound inventory and the exact version of it, the
#: policy identity and version, and the declared decision-relevant budgets.
MANIFEST_INPUT: tuple[str, ...] = (
    "inventory_ref",
    "inventory_output_digest",
    "policy_id",
    "policy_version",
    "budgets",
)

#: The selection semantics: mode, completeness, the structured technical cause when the selection
#: stopped short, the ordered selections and the exclusion summary. ``incompleteness`` belongs
#: here rather than to the envelope because it is part of what the selection *is*: two manifests
#: that selected the same pages, one of them having been cut off by a budget, are not the same
#: selection and must not share an output digest.
MANIFEST_OUTPUT: tuple[str, ...] = (
    "mode",
    "selection_complete",
    "incompleteness",
    "selections",
    "exclusions",
)

#: ``contract -> {class name -> members}``. The coverage test reads this against the schemas.
CLASSIFICATION: dict[str, dict[str, tuple[str, ...]]] = {
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


# --- the projections -------------------------------------------------------------------------


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
    """The inventory's stable semantics, with every order-independent collection sorted.

    The semantic-key gate runs first and refuses the document outright. ``sorted`` is stable, so
    two sources sharing a ``source_id`` or two candidates sharing a ``url_key`` would be left in
    the order they arrived in — and the digest of a set would silently become a digest of a
    sequence. Refusing is the only answer that keeps "canonical" true.
    """
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

    The observation *shape* is illustrative test data and deliberately not a contract: what a
    discovery runtime hands the inventory builder is PXAPI-19.B's decision. What is being proved
    here is the rule the inventory's ``input_digest`` declares — that enumeration order cannot
    change the digest — so the projection sorts rather than preserving the order it was given.
    """
    return sorted(
        (dict(observation) for observation in observations),
        key=itemgetter("observed_form", "source_id"),
    )


def manifest_input_projection(document: dict[str, Any]) -> dict[str, Any]:
    """What the selection was decided from. ``budgets`` is omitted when none was declared."""
    return {member: document[member] for member in MANIFEST_INPUT if member in document}


def manifest_output_projection(document: dict[str, Any]) -> dict[str, Any]:
    """The selection semantics: selections in rank order, exclusions in canonical order.

    The ranks and not the array positions carry the order, so re-serialising the document with
    its selections in another sequence cannot change what the manifest means. Exclusions are a
    per-reason summary and carry no order at all, so they are sorted.

    The semantic-key gate runs first, for the same reason it guards the inventory: a repeated
    rank, a repeated selected identity or a repeated exclusion reason leaves ``sorted`` breaking
    the tie by input order, which would make this digest depend on a serialisation accident.

    ``incompleteness`` participates and is omitted when the selection ran to its end — the
    contract admits it only alongside ``selection_complete: false``, so projecting a member that
    is not there would invent one.
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


# --- the illustrative discovery input behind each registered inventory example ----------------

#: ``inventory_id -> the admitted discovery observations that inventory was built from``.
#:
#: This is the one piece of data in this module that is not derived from the contracts, and it
#: exists so that every digest in every registered example is reproducible from repository
#: content rather than being a plausible-looking constant. The shape is illustrative: PXAPI-19.A
#: registers no observation contract, and a later slice is free to choose another.
ILLUSTRATIVE_DISCOVERY_INPUT: dict[str, list[dict[str, str]]] = {
    "inv-01JQ8Z4K2M0000000000000019": [
        {"observed_form": "https://example.com", "source_id": "CANONICAL_SEED"},
        {"observed_form": "https://example.com/", "source_id": "SITEMAP"},
        {"observed_form": "https://example.com/", "source_id": "SAME_ORIGIN_PAGE_LINKS"},
        {"observed_form": "https://example.com/leistungen", "source_id": "SITEMAP"},
        {
            "observed_form": "https://example.com/leistungen?utm_source=newsletter",
            "source_id": "SAME_ORIGIN_PAGE_LINKS",
        },
        {"observed_form": "https://example.com/referenzen", "source_id": "SITEMAP"},
        {"observed_form": "https://example.com/kontakt", "source_id": "SAME_ORIGIN_PAGE_LINKS"},
        {"observed_form": "https://example.com/broschuere.pdf", "source_id": "SITEMAP"},
    ],
    "inv-01JQ8Z4K2M0000000000000020": [
        {"observed_form": "https://example.org/", "source_id": "CANONICAL_SEED"},
    ],
    "inv-01JQ8Z4K2M0000000000000021": [
        {"observed_form": "https://example.net/", "source_id": "CANONICAL_SEED"},
        {
            "observed_form": "https://cdn.example.net/assets/index",
            "source_id": "SAME_ORIGIN_PAGE_LINKS",
        },
    ],
}
