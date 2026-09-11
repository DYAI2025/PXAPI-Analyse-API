"""The shipped digest producer: equivalent to the 19.A reference, and reproducing its examples.

The strongest available evidence is used first. Every digest in every registered acquisition
example was computed by the 19.A reference from repository content; the producer is required to
reproduce each of them exactly, from the same inputs. Equivalence of the projections and of the
member classification then pins *why* the values agree, so an accidental agreement on six
documents cannot hide a different rule.
"""

from __future__ import annotations

import copy
import random
from typing import Any

import pytest

from pxapi.domain import acquisition_digests as production
from pxapi.domain.acquisition_semantics import SemanticAmbiguity
from tests.acquisition import digests as reference
from tests.contracts.support import CONTRACTS, load_json

EXAMPLES = CONTRACTS.path / "examples"
INVENTORY_EXAMPLES = (
    "site-inventory",
    "site-inventory.homepage-only",
    "site-inventory.discovery-unavailable",
)
MANIFEST_EXAMPLES = (
    "sampling-manifest",
    "sampling-manifest.bounded-selection",
    "sampling-manifest.stratified-sample",
)


def example(name: str) -> dict[str, Any]:
    return load_json(EXAMPLES / f"{name}.example.json")


# --- the registered digests, reproduced -------------------------------------------------------


@pytest.mark.parametrize("name", INVENTORY_EXAMPLES)
def test_the_producer_reproduces_every_registered_inventory_digest(name: str) -> None:
    document = example(name)
    observations = reference.ILLUSTRATIVE_DISCOVERY_INPUT[document["inventory_id"]]
    assert production.inventory_digests(document, observations) == (
        document["input_digest"],
        document["output_digest"],
    )


@pytest.mark.parametrize("name", MANIFEST_EXAMPLES)
def test_the_producer_reproduces_every_registered_manifest_digest(name: str) -> None:
    document = example(name)
    assert production.manifest_digests(document) == (
        document["input_digest"],
        document["output_digest"],
    )


# --- equivalence of the rule behind the values ------------------------------------------------


def test_the_member_classification_is_the_19a_classification() -> None:
    assert production.CLASSIFICATION == reference.CLASSIFICATION


def test_the_canonical_form_and_the_algorithm_are_the_19a_ones() -> None:
    assert production.CANONICAL_JSON_OPTIONS == reference.CANONICAL_JSON_OPTIONS
    assert production.DIGEST_PREFIX == reference.DIGEST_PREFIX


@pytest.mark.parametrize("name", INVENTORY_EXAMPLES)
def test_the_inventory_projections_equal_the_reference_projections(name: str) -> None:
    document = example(name)
    observations = reference.ILLUSTRATIVE_DISCOVERY_INPUT[document["inventory_id"]]
    assert production.inventory_output_projection(document) == (
        reference.inventory_output_projection(document)
    )
    assert production.observation_input_projection(observations) == (
        reference.observation_input_projection(observations)
    )


@pytest.mark.parametrize("name", MANIFEST_EXAMPLES)
def test_the_manifest_projections_equal_the_reference_projections(name: str) -> None:
    document = example(name)
    assert production.manifest_input_projection(document) == (
        reference.manifest_input_projection(document)
    )
    assert production.manifest_output_projection(document) == (
        reference.manifest_output_projection(document)
    )


@pytest.mark.parametrize("contract", sorted(production.CLASSIFICATION))
def test_every_root_member_of_the_contract_has_exactly_one_digest_class(contract: str) -> None:
    schema = load_json(CONTRACTS.schema_path(contract))
    classes = production.CLASSIFICATION[contract]
    members = [member for group in classes.values() for member in group]
    assert sorted(members) == sorted(schema["properties"])
    assert len(members) == len(set(members))


# --- determinism --------------------------------------------------------------------------


def test_the_envelope_never_participates_in_either_digest() -> None:
    document = example("site-inventory")
    observations = reference.ILLUSTRATIVE_DISCOVERY_INPUT[document["inventory_id"]]
    renamed = dict(
        document, run_id="run-other", inventory_id="inv-other", generated_at="2031-01-01T00:00:00Z"
    )
    assert production.inventory_digests(renamed, observations) == (
        production.inventory_digests(document, observations)
    )
    manifest = example("sampling-manifest")
    renamed_manifest = dict(
        manifest, run_id="r", sampling_manifest_id="s", generated_at="2031-01-01T00:00:00Z"
    )
    assert production.manifest_digests(renamed_manifest) == production.manifest_digests(manifest)


def test_no_enumeration_order_can_change_an_inventory_digest() -> None:
    document = example("site-inventory")
    observations = reference.ILLUSTRATIVE_DISCOVERY_INPUT[document["inventory_id"]]
    expected = production.inventory_digests(document, observations)
    shuffler = random.Random(19)
    for _ in range(25):
        shuffled = copy.deepcopy(document)
        for member in ("sources", "candidates"):
            shuffler.shuffle(shuffled[member])
        for candidate in shuffled["candidates"]:
            shuffler.shuffle(candidate["observed_forms"])
            shuffler.shuffle(candidate["provenance"])
        reordered = list(observations)
        shuffler.shuffle(reordered)
        assert production.inventory_digests(shuffled, reordered) == expected


@pytest.mark.parametrize("name", MANIFEST_EXAMPLES)
def test_the_rank_and_not_the_array_position_orders_a_manifest_digest(name: str) -> None:
    """Re-serialising the arrays in another order changes nothing; moving a rank does."""
    document = example(name)
    reordered = copy.deepcopy(document)
    reordered["selections"].reverse()
    reordered["exclusions"].reverse()
    assert production.manifest_digests(reordered) == (
        document["input_digest"],
        document["output_digest"],
    )
    reranked = copy.deepcopy(document)
    first, second = reranked["selections"][0], reranked["selections"][1]
    first["selection_rank"], second["selection_rank"] = (
        second["selection_rank"],
        first["selection_rank"],
    )
    assert production.manifest_digests(reranked)[1] != document["output_digest"]


def test_a_semantic_change_does_change_the_output_digest() -> None:
    """Canary: a digest that never changed would satisfy every determinism test above."""
    document = example("site-inventory")
    changed = copy.deepcopy(document)
    changed["candidates"][1]["page_type"] = "PROOF"
    assert production.inventory_output_projection(changed) != (
        production.inventory_output_projection(document)
    )
    assert (
        production.digest_of(production.inventory_output_projection(changed))
        != (document["output_digest"])
    )


def test_an_ambiguous_document_receives_no_digest() -> None:
    document = example("site-inventory")
    document["candidates"].append(
        dict(document["candidates"][1], observed_forms=["https://example.com/x"])
    )
    with pytest.raises(SemanticAmbiguity):
        production.inventory_output_projection(document)


def test_a_floating_point_value_cannot_be_digested() -> None:
    with pytest.raises(ValueError):
        production.canonical_json({"value": float("nan")})
    assert production.floats_in({"a": [1, 2.5, True]}) == ["/a/1"]
