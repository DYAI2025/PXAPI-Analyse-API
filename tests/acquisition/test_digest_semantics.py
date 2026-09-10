"""The digest topology of the two acquisition contracts, and the rules the digests declare.

PXAPI-19.A registers contracts and no producer, so nothing shipped computes a digest here. What
is provable without one is the part that actually goes wrong later: *which* members a digest is
computed over, that the serialisation is deterministic, that an order-independent collection
cannot silently make a digest order-dependent, and that an envelope identity, a clock reading or
a digest member itself never participates. ``tests.acquisition.digests`` is the reference
implementation of those rules and this module is the proof.

The member classification is derived against the schemas rather than trusted: a member added to
either contract without a decision about whether it participates in a digest turns this module
red instead of silently digesting or silently escaping.
"""

from __future__ import annotations

import itertools
import json
from typing import Any

import pytest

from tests.acquisition.digests import (
    CLASSIFICATION,
    DIGEST_PREFIX,
    ILLUSTRATIVE_DISCOVERY_INPUT,
    SAMPLING_MANIFEST,
    SITE_INVENTORY,
    canonical_json,
    digest_of,
    floats_in,
    inventory_output_projection,
    manifest_input_projection,
    manifest_output_projection,
    observation_input_projection,
)
from tests.contracts.support import CONTRACTS, load_json

CONTRACT_NAMES = (SITE_INVENTORY, SAMPLING_MANIFEST)

#: The digest members every one of the two contracts must carry, and the one it must not.
REQUIRED_DIGESTS = ("input_digest", "output_digest")
FORBIDDEN_DIGEST = "content_digest"

#: The shared definition every digest-shaped member resolves to.
DIGEST_REF = "urn:pxapi:schema:acquisition:1.0.0#/$defs/digest"


def schema_of(contract: str) -> dict[str, Any]:
    return load_json(CONTRACTS.schema_path(contract))


def examples_of(contract: str) -> list[dict[str, Any]]:
    return [load_json(path) for path in CONTRACTS.example_paths(contract)]


def _property_names(node: Any) -> set[str]:
    """Every declared member name anywhere in a schema, at any depth."""
    names: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                names |= set(value)
                for member in value.values():
                    names |= _property_names(member)
            else:
                names |= _property_names(value)
    elif isinstance(node, list):
        for value in node:
            names |= _property_names(value)
    return names


def _mutate(value: Any) -> Any:
    """A different value of the same kind, used to prove a digest is sensitive to a member.

    A list is shortened rather than reordered: reordering an order-independent collection must
    *not* change a digest, and that is a separate proof below.
    """
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, str):
        return value + "-mutated"
    if isinstance(value, list):
        return value[:-1]
    if isinstance(value, dict):
        return {key: _mutate(item) for key, item in value.items()}
    raise AssertionError(f"no mutation defined for {type(value)!r}")


def _projections(contract: str, document: dict[str, Any]) -> dict[str, Any]:
    """The input and output projections of one document of ``contract``."""
    if contract == SITE_INVENTORY:
        return {"output": inventory_output_projection(document)}
    return {
        "input": manifest_input_projection(document),
        "output": manifest_output_projection(document),
    }


# --- canaries -------------------------------------------------------------------------------


def test_both_contracts_are_registered_and_carry_examples() -> None:
    """Without this, every parametrised proof below would pass over an empty list."""
    for contract in CONTRACT_NAMES:
        assert CONTRACTS.has_contract(contract), contract
        assert examples_of(contract), f"{contract} registers no example"


def test_the_canonical_serialisation_sorts_keys_and_encodes_utf8() -> None:
    """Canary for the serialiser every digest below is computed through."""
    assert canonical_json({"b": 1, "a": [2, 1]}) == b'{"a":[2,1],"b":1}'
    assert canonical_json({"t": "Bäckerei"}) == '{"t":"Bäckerei"}'.encode()
    assert digest_of({}).startswith(DIGEST_PREFIX)
    assert len(digest_of({})) == len(DIGEST_PREFIX) + 64


def test_the_canonical_serialisation_refuses_a_non_json_constant() -> None:
    """NaN is not JSON and every numeric bound compares False against it; it must not serialise."""
    for value in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            canonical_json({"value": value})


def test_the_float_scanner_sees_a_planted_float() -> None:
    """Canary: the no-floating-point proofs below must detect one if it existed."""
    assert floats_in({"a": [1, {"b": 2.5}]}) == ["/a/1/b"]
    assert floats_in({"a": [1, {"b": True}]}) == []


def test_the_mutator_changes_every_kind_of_member_the_contracts_use() -> None:
    """Canary: a mutation that returned the value unchanged would make the sensitivity proof
    vacuous."""
    for value in ("text", 3, True, ["a", "b"], {"k": 1}):
        assert _mutate(value) != value


# --- the member classification ---------------------------------------------------------------


@pytest.mark.parametrize("contract", CONTRACT_NAMES)
def test_every_root_member_is_classified_exactly_once(contract: str) -> None:
    """A member nobody classified would digest, or escape a digest, without a decision."""
    declared = set(schema_of(contract)["properties"])
    classes = CLASSIFICATION[contract]
    classified = [member for members in classes.values() for member in members]
    assert set(classified) == declared, (
        f"{contract}: unclassified {sorted(declared - set(classified))}, "
        f"stale {sorted(set(classified) - declared)}"
    )
    assert len(classified) == len(set(classified)), f"{contract}: a member is in two classes"


@pytest.mark.parametrize("contract", CONTRACT_NAMES)
def test_the_classification_actually_classifies_something(contract: str) -> None:
    classes = CLASSIFICATION[contract]
    assert classes["ENVELOPE"] and classes["DIGEST"] and classes["OUTPUT"]


def test_only_the_inventory_leaves_its_input_outside_the_document() -> None:
    """The asymmetry is deliberate and stated: the inventory's input is the admitted discovery
    observations, which it does not carry, while the manifest's input is the binding, the policy
    and the budgets, which it does."""
    assert CLASSIFICATION[SITE_INVENTORY]["INPUT"] == ()
    assert CLASSIFICATION[SAMPLING_MANIFEST]["INPUT"]


# --- the digest topology ---------------------------------------------------------------------


@pytest.mark.parametrize("contract", CONTRACT_NAMES)
def test_the_contract_carries_both_required_digests_and_no_content_digest(contract: str) -> None:
    """D-PXAPI19-PO-004: input and output are the whole topology."""
    schema = schema_of(contract)
    for member in REQUIRED_DIGESTS:
        assert member in schema["properties"], f"{contract} declares no {member}"
        assert member in schema["required"], f"{contract}: {member} must be required"
    assert FORBIDDEN_DIGEST not in _property_names(schema), (
        f"{contract} declares {FORBIDDEN_DIGEST}, which D-PXAPI19-PO-004 forbids"
    )


@pytest.mark.parametrize("contract", CONTRACT_NAMES)
def test_every_digest_member_uses_the_one_shared_digest_shape(contract: str) -> None:
    schema = schema_of(contract)
    for member in REQUIRED_DIGESTS:
        assert schema["properties"][member]["$ref"] == DIGEST_REF, f"{contract}.{member}"


@pytest.mark.parametrize("contract", CONTRACT_NAMES)
def test_the_two_digests_document_different_roles(contract: str) -> None:
    """A topology of two digests is worthless if the contract does not say which is which."""
    declared = schema_of(contract)["properties"]
    incoming = declared["input_digest"]["description"]
    outgoing = declared["output_digest"]["description"]
    assert incoming != outgoing, f"{contract}: the two digests carry the same description"
    assert "input" in incoming and "output" in outgoing
    for description in (incoming, outgoing):
        assert "Envelope identities and timestamps" in description, (
            f"{contract}: a digest description must state what does not participate"
        )


#: Values that are not a canonical digest. Upper-case hexadecimal is refused so that one byte
#: sequence has exactly one written digest; a bare hex string is refused so no reader has to
#: assume an algorithm; a foreign prefix is refused because a later algorithm is a new contract
#: version rather than a widened shape.
MALFORMED_DIGESTS = [
    "ab" * 32,
    "sha256:" + "AB" * 32,
    "sha512:" + "ab" * 32,
    "sha256:" + "ab" * 31,
    "sha256:" + "ab" * 33,
    "sha256:",
    "",
]


@pytest.mark.parametrize("contract", CONTRACT_NAMES)
@pytest.mark.parametrize("member", REQUIRED_DIGESTS)
@pytest.mark.parametrize("value", MALFORMED_DIGESTS, ids=repr)
def test_a_value_outside_the_canonical_digest_shape_is_refused(
    contract: str, member: str, value: str
) -> None:
    document = dict(examples_of(contract)[0], **{member: value})
    keys = {violation.key for violation in CONTRACTS.validate(contract, document)}
    assert keys & {
        (f"/{member}", "pattern"),
        (f"/{member}", "minLength"),
        (f"/{member}", "maxLength"),
    }, f"{contract}.{member} accepted {value!r}"


@pytest.mark.parametrize("contract", CONTRACT_NAMES)
def test_no_declared_member_admits_a_floating_point_number(contract: str) -> None:
    """A digest over a float is not portable between producers, so none is representable."""
    text = json.dumps(schema_of(contract))
    assert '"type": "number"' not in text and '"type":"number"' not in text, contract


EXAMPLE_CASES = [
    (contract, path.name, index)
    for contract in CONTRACT_NAMES
    for index, path in enumerate(CONTRACTS.example_paths(contract))
]
EXAMPLE_IDS = [name for _, name, _ in EXAMPLE_CASES]


@pytest.mark.parametrize(("contract", "name", "index"), EXAMPLE_CASES, ids=EXAMPLE_IDS)
def test_no_registered_example_carries_a_floating_point_value(
    contract: str, name: str, index: int
) -> None:
    document = examples_of(contract)[index]
    assert floats_in(document) == [], f"{name}: floating-point member(s)"


# --- the registered examples are reproducible ------------------------------------------------


def test_every_registered_inventory_example_carries_its_computed_output_digest() -> None:
    """Not decoration: each example's digest is recomputed here from the example's own content."""
    for document in examples_of(SITE_INVENTORY):
        expected = digest_of(inventory_output_projection(document))
        assert document["output_digest"] == expected, document["inventory_id"]


def test_every_registered_inventory_example_carries_its_computed_input_digest() -> None:
    """Computed over the illustrative admitted observations declared for that example."""
    for document in examples_of(SITE_INVENTORY):
        observations = ILLUSTRATIVE_DISCOVERY_INPUT[document["inventory_id"]]
        expected = digest_of(observation_input_projection(observations))
        assert document["input_digest"] == expected, document["inventory_id"]


def test_every_registered_manifest_example_carries_its_computed_digests() -> None:
    for document in examples_of(SAMPLING_MANIFEST):
        assert document["input_digest"] == digest_of(manifest_input_projection(document))
        assert document["output_digest"] == digest_of(manifest_output_projection(document))


def test_every_registered_manifest_binds_the_exact_output_digest_of_its_inventory() -> None:
    """The cross-document binding, checked rather than asserted in prose."""
    inventories = {
        document["inventory_id"]: document["output_digest"]
        for document in examples_of(SITE_INVENTORY)
    }
    for document in examples_of(SAMPLING_MANIFEST):
        bound = document["inventory_ref"]
        assert bound in inventories, f"{document['sampling_manifest_id']}: unknown inventory"
        assert document["inventory_output_digest"] == inventories[bound]


def test_two_inventories_of_different_sites_do_not_share_an_output_digest() -> None:
    """Canary: a projection that dropped its content would digest everything identically."""
    digests = {document["output_digest"] for document in examples_of(SITE_INVENTORY)}
    assert len(digests) == len(examples_of(SITE_INVENTORY))


# --- order independence, and the one place order is semantic ---------------------------------


def test_reordering_the_inventory_sources_leaves_the_output_digest_unchanged() -> None:
    document = examples_of(SITE_INVENTORY)[0]
    assert len(document["sources"]) > 1, "canary: nothing to reorder"
    for permutation in itertools.permutations(document["sources"]):
        candidate = dict(document, sources=list(permutation))
        assert digest_of(inventory_output_projection(candidate)) == document["output_digest"]


def test_reordering_the_inventory_candidates_leaves_the_output_digest_unchanged() -> None:
    document = examples_of(SITE_INVENTORY)[0]
    assert len(document["candidates"]) > 1, "canary: nothing to reorder"
    candidate = dict(document, candidates=list(reversed(document["candidates"])))
    assert digest_of(inventory_output_projection(candidate)) == document["output_digest"]


def test_reordering_a_candidates_own_collections_leaves_the_output_digest_unchanged() -> None:
    """``observed_forms`` and ``provenance`` are sets the contract renders as arrays."""
    document = examples_of(SITE_INVENTORY)[0]
    reordered = []
    touched = 0
    for entry in document["candidates"]:
        item = dict(entry)
        for member in ("observed_forms", "provenance"):
            if len(item[member]) > 1:
                item[member] = list(reversed(item[member]))
                touched += 1
        reordered.append(item)
    assert touched > 0, "canary: no multi-valued collection to reorder"
    candidate = dict(document, candidates=reordered)
    assert digest_of(inventory_output_projection(candidate)) == document["output_digest"]


def _orderings(observations: list[dict[str, str]]) -> list[list[dict[str, str]]]:
    """Every ordering of a short list; the list and its reverse for a longer one.

    Exhausting the permutations of the eight-observation example would be 40320 digests for no
    extra proof, so the reversal stands in there.
    """
    if len(observations) <= 4:
        return [list(permutation) for permutation in itertools.permutations(observations)]
    return [list(observations), list(reversed(observations))]


def test_the_admitted_observation_input_digest_is_enumeration_order_independent() -> None:
    """The rule the inventory's ``input_digest`` declares, over every registered example."""
    checked = 0
    for document in examples_of(SITE_INVENTORY):
        observations = ILLUSTRATIVE_DISCOVERY_INPUT[document["inventory_id"]]
        digests = {
            digest_of(observation_input_projection(ordering))
            for ordering in _orderings(observations)
        }
        assert digests == {document["input_digest"]}, document["inventory_id"]
        checked += len(_orderings(observations))
    assert checked > len(examples_of(SITE_INVENTORY)), "canary: no reordering was exercised"


def test_reordering_the_selections_array_leaves_the_manifest_output_digest_unchanged() -> None:
    """The ranks carry the order, so a re-serialisation cannot change what a manifest means."""
    for document in examples_of(SAMPLING_MANIFEST):
        if len(document["selections"]) < 2:
            continue
        candidate = dict(document, selections=list(reversed(document["selections"])))
        assert digest_of(manifest_output_projection(candidate)) == document["output_digest"]


def test_permuting_the_selection_ranks_changes_the_manifest_output_digest() -> None:
    """Selection order *is* semantic here: the digest must not be blind to it."""
    changed = 0
    for document in examples_of(SAMPLING_MANIFEST):
        selections = document["selections"]
        if len(selections) < 2:
            continue
        ranks = [entry["selection_rank"] for entry in selections]
        swapped = [
            dict(entry, selection_rank=rank)
            for entry, rank in zip(selections, list(reversed(ranks)), strict=True)
        ]
        candidate = dict(document, selections=swapped)
        assert digest_of(manifest_output_projection(candidate)) != document["output_digest"]
        changed += 1
    assert changed > 0, "canary: no manifest had two selections to permute"


def test_reordering_the_exclusion_summary_leaves_the_manifest_output_digest_unchanged() -> None:
    reordered = 0
    for document in examples_of(SAMPLING_MANIFEST):
        if len(document["exclusions"]) < 2:
            continue
        candidate = dict(document, exclusions=list(reversed(document["exclusions"])))
        assert digest_of(manifest_output_projection(candidate)) == document["output_digest"]
        reordered += 1
    assert reordered > 0, "canary: no manifest had two exclusion reasons to reorder"


# --- what never participates, and what always does -------------------------------------------

ENVELOPE_CASES = [
    (contract, member)
    for contract in CONTRACT_NAMES
    for member in CLASSIFICATION[contract]["ENVELOPE"] + CLASSIFICATION[contract]["DIGEST"]
]
ENVELOPE_IDS = [f"{contract}.{member}" for contract, member in ENVELOPE_CASES]


@pytest.mark.parametrize(("contract", "member"), ENVELOPE_CASES, ids=ENVELOPE_IDS)
def test_an_envelope_or_digest_member_never_participates_in_a_digest(
    contract: str, member: str
) -> None:
    """Re-emitting the same semantics under a new id at a new instant changes no digest."""
    document = examples_of(contract)[0]
    baseline = _projections(contract, document)
    candidate = dict(document, **{member: _mutate(document[member])})
    assert _projections(contract, candidate) == baseline, f"{contract}.{member} leaked"


SENSITIVE_CASES = [
    (contract, class_name, member)
    for contract in CONTRACT_NAMES
    for class_name in ("INPUT", "OUTPUT")
    for member in CLASSIFICATION[contract][class_name]
]
SENSITIVE_IDS = [f"{c}.{m}" for c, _, m in SENSITIVE_CASES]


def test_there_is_a_digest_relevant_member_to_check() -> None:
    assert SENSITIVE_CASES, "canary: no digest-relevant member is exercised at all"


@pytest.mark.parametrize(("contract", "class_name", "member"), SENSITIVE_CASES, ids=SENSITIVE_IDS)
def test_changing_a_digest_relevant_member_changes_its_digest(
    contract: str, class_name: str, member: str
) -> None:
    """A member classified as participating must actually participate."""
    document = next(example for example in examples_of(contract) if member in example)
    projection = "input" if class_name == "INPUT" else "output"
    baseline = _projections(contract, document)[projection]
    candidate = dict(document, **{member: _mutate(document[member])})
    assert _projections(contract, candidate)[projection] != baseline, (
        f"{contract}.{member} is classified {class_name} but does not affect that digest"
    )
