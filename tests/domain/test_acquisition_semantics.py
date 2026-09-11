"""Producer-side enforcement of the 19.A invariants, proved equivalent to the 19.A reference.

Two things are proved, and they are kept apart on purpose.

**Equivalence.** The production contract-semantic layer returns the same verdict as the 19.A
reference in ``tests/acquisition/semantics.py`` — rule for rule, pointer for pointer — on every
registered example, every 19.A counterexample and a corpus of structural mutations. The
reference stays exactly as 19.A merged it; this file is what binds the producer to it.

**Producer guarantees.** Every rule this producer adds has a counterexample that fires exactly
that rule and no other, and a coverage test turns red if a rule is declared without one.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pxapi.domain import acquisition_semantics as production
from pxapi.domain.acquisition_semantics import (
    SAMPLING_MANIFEST,
    SITE_INVENTORY,
    ProducerInvariantViolated,
    SemanticAmbiguity,
    inventory_producer_violations,
    manifest_producer_violations,
    require_emittable_inventory,
    require_emittable_manifest,
)
from tests.acquisition import semantics as reference
from tests.contracts.support import CONTRACTS, load_json

FIXTURES = Path(__file__).resolve().parents[1] / "acquisition" / "fixtures" / "semantic-invalid"
EXAMPLES = CONTRACTS.path / "examples"


def example(name: str) -> dict[str, Any]:
    return load_json(EXAMPLES / f"{name}.example.json")


INVENTORY = example("site-inventory")
MANIFEST = example("sampling-manifest")
BOUNDED = example("sampling-manifest.bounded-selection")
STRATIFIED = example("sampling-manifest.stratified-sample")

Mutation = Callable[[dict[str, Any]], None]


def mutated(document: dict[str, Any], change: Mutation) -> dict[str, Any]:
    copied = copy.deepcopy(document)
    change(copied)
    return copied


# --- equivalence with the 19.A reference ----------------------------------------------------


def _fixture_documents() -> list[tuple[str, str, dict[str, Any]]]:
    found = []
    for contract_dir in sorted(p for p in FIXTURES.iterdir() if p.is_dir()):
        for path in sorted(contract_dir.glob("*.json")):
            if path.name != "expectations.json":
                found.append((contract_dir.name, path.stem, load_json(path)))
    return found


INVENTORY_MUTATIONS: dict[str, Mutation] = {
    "unchanged": lambda d: None,
    "repeated-source": lambda d: d["sources"].append(dict(d["sources"][0])),
    "repeated-source-other-outcome": lambda d: d["sources"].append(
        dict(d["sources"][2], outcome="ABSENT", candidate_count=0)
    ),
    "repeated-candidate": lambda d: d["candidates"].append(
        dict(d["candidates"][1], observed_forms=["https://example.com/leistungen"])
    ),
    "source-without-id": lambda d: d["sources"][0].pop("source_id"),
    "sources-not-a-list": lambda d: d.update(sources={}),
    "candidate-not-an-object": lambda d: d["candidates"].append("x"),
}

MANIFEST_MUTATIONS: dict[str, Mutation] = {
    "unchanged": lambda d: None,
    "repeated-identity": lambda d: d["selections"][1].update(url_key=d["selections"][0]["url_key"]),
    "repeated-rank": lambda d: d["selections"][1].update(selection_rank=1),
    "gapped-rank": lambda d: d["selections"][-1].update(selection_rank=9),
    "rank-zero": lambda d: d["selections"][0].update(selection_rank=0),
    "rank-as-boolean": lambda d: d["selections"][0].update(selection_rank=True),
    "rank-null": lambda d: d["selections"][0].update(selection_rank=None),
    "repeated-reason": lambda d: d["exclusions"].append(dict(d["exclusions"][0])),
    "no-selections": lambda d: d.update(selections=[]),
    "selections-not-a-list": lambda d: d.update(selections="x"),
    "exclusion-without-reason": lambda d: d["exclusions"][0].pop("reason"),
}


def _corpus() -> list[tuple[str, str, dict[str, Any]]]:
    corpus = list(_fixture_documents())
    for name, change in INVENTORY_MUTATIONS.items():
        corpus.append((SITE_INVENTORY, f"mutation/{name}", mutated(INVENTORY, change)))
    for base_name, base in (("full", MANIFEST), ("bounded", BOUNDED), ("stratified", STRATIFIED)):
        for name, change in MANIFEST_MUTATIONS.items():
            corpus.append((SAMPLING_MANIFEST, f"{base_name}/{name}", mutated(base, change)))
    for name in ("site-inventory.homepage-only", "site-inventory.discovery-unavailable"):
        corpus.append((SITE_INVENTORY, f"example/{name}", example(name)))
    return corpus


CORPUS = _corpus()


def test_the_equivalence_corpus_holds_both_verdicts() -> None:
    """Canary: a corpus of only clean documents would make equivalence vacuously true."""
    verdicts = {bool(reference.violations_of(c, d)) for c, _, d in CORPUS}
    assert verdicts == {True, False}


@pytest.mark.parametrize(
    ("contract", "case", "document"), CORPUS, ids=[f"{c}/{n}" for c, n, _ in CORPUS]
)
def test_the_producer_agrees_with_the_19a_reference_rule_for_rule(
    contract: str, case: str, document: dict[str, Any]
) -> None:
    produced = [v.key for v in production.violations_of(contract, document)]
    expected = [v.key for v in reference.violations_of(contract, document)]
    assert produced == expected


def test_the_producer_states_exactly_the_19a_rule_set() -> None:
    assert production.CONTRACT_RULES == reference.RULES
    assert production.CONTRACT_RULES_BY_CONTRACT == reference.RULES_BY_CONTRACT


@pytest.mark.parametrize(
    ("contract", "case", "document"),
    _fixture_documents(),
    ids=[f"{c}/{n}" for c, n, _ in _fixture_documents()],
)
def test_the_producer_refuses_every_19a_counterexample_with_its_recorded_violations(
    contract: str, case: str, document: dict[str, Any]
) -> None:
    expectations = load_json(FIXTURES / contract / "expectations.json")["cases"][case]
    expected = {(v["pointer"], v["rule"]) for v in expectations["violations"]}
    with pytest.raises(SemanticAmbiguity) as refused:
        production.require_unambiguous(contract, document)
    assert refused.value.keys == expected


def test_an_unknown_contract_is_refused_rather_than_reported_clean() -> None:
    with pytest.raises(KeyError):
        production.violations_of("not-a-contract", {})


# --- the producer guarantees ------------------------------------------------------------------


def _drop_seed_provenance(d: dict[str, Any]) -> None:
    d["candidates"][0]["provenance"].remove("CANONICAL_SEED")
    d["sources"][0]["candidate_count"] = 0


INVENTORY_COUNTEREXAMPLES: dict[str, Mutation] = {
    "seed_candidate_present": _drop_seed_provenance,
    "seed_candidate_eligible": lambda d: d["candidates"][0].update(
        eligibility={"state": "EXCLUDED", "exclusion_reason": "OFF_ORIGIN"}
    ),
    "admitting_outcome_for_contributed_source": lambda d: d["sources"][2].update(outcome="ABSENT"),
    "source_declared_for_every_provenance": lambda d: d["sources"].pop(3),
    "candidate_count_matches_provenance": lambda d: d["sources"][2].update(candidate_count=5),
    "source_id_is_a_code": lambda d: d["sources"][1].update(source_id="robots"),
}

MANIFEST_COUNTEREXAMPLES: dict[str, tuple[dict[str, Any], Mutation]] = {
    "selection_is_an_inventory_candidate": (
        MANIFEST,
        lambda d: d["selections"][1].update(url_key="https://example.com/nowhere"),
    ),
    "selection_is_eligible_in_inventory": (
        MANIFEST,
        lambda d: d["selections"][1].update(url_key="https://example.com/broschuere.pdf"),
    ),
    "every_selection_carries_a_stratum": (
        MANIFEST,
        lambda d: d["selections"][1].update(stratum=""),
    ),
    "exclusions_account_for_the_remainder": (
        MANIFEST,
        lambda d: d["exclusions"][0].update(candidate_count=2),
    ),
    "incompleteness_matches_completeness": (
        MANIFEST,
        lambda d: d.update(selection_complete=False),
    ),
    "budget_cause_declares_its_budget": (BOUNDED, lambda d: d.pop("budgets")),
    "census_never_emits_a_sample": (STRATIFIED, lambda d: None),
}


def test_the_code_shape_is_the_contract_code_shape_verbatim() -> None:
    code = load_json(CONTRACTS.schema_path("common"))["$defs"]["code"]
    assert code["pattern"] == production.CODE_PATTERN
    assert code["maxLength"] == production.CODE_MAX_LENGTH


def test_the_registered_census_documents_satisfy_every_producer_guarantee() -> None:
    """The baseline the counterexamples depart from is itself clean, or none would prove much."""
    assert inventory_producer_violations(INVENTORY) == ()
    assert manifest_producer_violations(MANIFEST, INVENTORY) == ()
    assert manifest_producer_violations(BOUNDED, INVENTORY) == ()


@pytest.mark.parametrize("rule", sorted(INVENTORY_COUNTEREXAMPLES))
def test_an_inventory_counterexample_fires_exactly_its_rule(rule: str) -> None:
    document = mutated(INVENTORY, INVENTORY_COUNTEREXAMPLES[rule])
    assert {v.rule for v in inventory_producer_violations(document)} == {rule}
    with pytest.raises(ProducerInvariantViolated):
        require_emittable_inventory(document)


@pytest.mark.parametrize("rule", sorted(MANIFEST_COUNTEREXAMPLES))
def test_a_manifest_counterexample_fires_exactly_its_rule(rule: str) -> None:
    base, change = MANIFEST_COUNTEREXAMPLES[rule]
    document = mutated(base, change)
    assert {v.rule for v in manifest_producer_violations(document, INVENTORY)} == {rule}
    with pytest.raises(ProducerInvariantViolated):
        require_emittable_manifest(document, INVENTORY)


def test_every_producer_rule_has_a_counterexample_and_every_counterexample_a_rule() -> None:
    proved = set(INVENTORY_COUNTEREXAMPLES) | set(MANIFEST_COUNTEREXAMPLES)
    assert proved == set(production.PRODUCER_RULES)


def test_a_complete_selection_that_also_names_a_cause_is_refused() -> None:
    document = mutated(
        MANIFEST, lambda d: d.update(incompleteness={"cause": "SAFETY_LIMIT_REACHED"})
    )
    assert {v.rule for v in manifest_producer_violations(document, INVENTORY)} == {
        "incompleteness_matches_completeness"
    }


def test_the_semantic_gate_runs_before_the_producer_guarantees() -> None:
    """An ambiguous document is refused as ambiguous, whatever else is wrong with it."""
    document = mutated(INVENTORY, INVENTORY_MUTATIONS["repeated-candidate"])
    with pytest.raises(SemanticAmbiguity):
        require_emittable_inventory(document)


@pytest.mark.parametrize(
    "junk",
    [
        {"candidates": "x", "sources": []},
        {
            "candidates": [{"eligibility": "ELIGIBLE", "url_key": "u"}],
            "sources": [],
            "target_origin": "u",
        },
        {
            "candidates": [{"url_key": "u", "provenance": ["CANONICAL_SEED"]}],
            "sources": ["x"],
            "target_origin": "u",
        },
    ],
)
def test_the_inventory_guarantees_never_crash_on_a_malformed_document(junk: dict[str, Any]) -> None:
    """A checker that raises TypeError reports nothing at all — the opposite of failing closed."""
    inventory_producer_violations(junk)


def test_the_manifest_guarantees_never_crash_on_a_malformed_document() -> None:
    junk = mutated(BOUNDED, lambda d: d.update(incompleteness="SELECTION_BUDGET_EXHAUSTED"))
    manifest_producer_violations(junk, INVENTORY)
    manifest_producer_violations(
        {"selections": [], "exclusions": [], "mode": "CENSUS"}, {"candidates": "x"}
    )


def test_the_semantic_gate_alone_refuses_a_document_every_producer_rule_accepts() -> None:
    """A repeated source with the same outcome and the same count breaks no producer guarantee,
    so only the semantic gate can refuse it — which isolates that gate from the rules after it."""
    document = mutated(INVENTORY, lambda d: d["sources"].append(dict(d["sources"][2])))
    assert inventory_producer_violations(document) == ()
    with pytest.raises(SemanticAmbiguity):
        require_emittable_inventory(document)
