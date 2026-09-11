"""The semantic-key rules bite, and the digest refuses an ambiguous document rather than guessing.

Three things are proved here, and the order matters because each depends on the one before it.

1. **JSON Schema does not enforce these relationships.** Every counterexample under
   ``fixtures/semantic-invalid/`` is asserted *schema-valid* before it is asserted semantically
   invalid. That pairing is the evidence: ``uniqueItems`` compares whole items, so a duplicate
   semantic key carried by items that differ in any other member passes it.
2. **The contract-semantic layer rejects them**, at a named rule and a JSON pointer rather than
   in free text, so an expectation cannot go red on a reworded message.
3. **The digest reference implementation fails closed on them.** ``sorted`` is stable: a
   duplicate key would leave the two entries in whatever order the producer emitted, and a
   canonical digest would quietly become a digest of an accident. The unguarded ordering is
   reconstructed here and shown to produce two different digests for two serialisations of one
   ambiguous document — which is what makes the guard load-bearing rather than decorative — and
   the guarded projection is shown to refuse both.

The mirror proof runs too: every registered example is unambiguous, and reordering an
order-independent collection of a *valid* document leaves its digest untouched.

PXAPI-19.A authorises no production validator, so this layer is test code. **Equivalent
producer-side enforcement is mandatory in PXAPI-19.B**: nothing in this slice prevents a producer
from emitting a document no consumer can order.
"""

from __future__ import annotations

import copy
import itertools
import json
from operator import itemgetter
from pathlib import Path
from typing import Any

import pytest

from tests.acquisition.digests import (
    digest_of,
    inventory_output_projection,
    manifest_output_projection,
)
from tests.acquisition.semantics import (
    RULES,
    RULES_BY_CONTRACT,
    SAMPLING_MANIFEST,
    SITE_INVENTORY,
    SemanticAmbiguity,
    SemanticViolation,
    require_unambiguous,
    violations_of,
)
from tests.contracts.support import CONTRACTS, load_json

CONTRACT_NAMES = (SITE_INVENTORY, SAMPLING_MANIFEST)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "semantic-invalid"
EXPECTATIONS_FILENAME = "expectations.json"

#: Which projection each contract's output digest is computed through, and the collections whose
#: canonical order that projection decides. Stated once so the ambiguity proofs below and the
#: order-independence proofs cannot disagree about what they are exercising.
PROJECTIONS = {
    SITE_INVENTORY: inventory_output_projection,
    SAMPLING_MANIFEST: manifest_output_projection,
}


class SemanticCase:
    """One semantic counterexample and the rules it is expected to break."""

    def __init__(self, contract: str, case: str, document_path: Path, expectation: Any) -> None:
        self.contract = contract
        self.case = case
        self.document_path = document_path
        self.expectation = expectation

    @property
    def id(self) -> str:
        return f"{self.contract}/{self.case}"

    def document(self) -> dict[str, Any]:
        return load_json(self.document_path)

    def expected_keys(self) -> set[tuple[str, str]]:
        return {(v["pointer"], v["rule"]) for v in (self.expectation or {}).get("violations", [])}


def _cases() -> list[SemanticCase]:
    """Every ``(contract, case)`` under the fixture root, paired with its expectation.

    A document with no expectation, and an expectation with no document, are both surfaced as a
    case with a missing half rather than skipped — an orphan that disappears from the run is the
    way a counterexample stops proving anything without anybody noticing.
    """
    found: list[SemanticCase] = []
    for contract_dir in sorted(p for p in FIXTURES_DIR.iterdir() if p.is_dir()):
        index_path = contract_dir / EXPECTATIONS_FILENAME
        index = load_json(index_path) if index_path.is_file() else {}
        expectations = dict(index.get("cases", {}))
        documents = {
            path.stem: path
            for path in sorted(contract_dir.glob("*.json"))
            if path.name != EXPECTATIONS_FILENAME
        }
        for case in sorted(set(documents) | set(expectations)):
            found.append(
                SemanticCase(
                    contract=contract_dir.name,
                    case=case,
                    document_path=documents.get(case),  # type: ignore[arg-type]
                    expectation=expectations.get(case),
                )
            )
    return found


CASES = _cases()
CASE_IDS = [case.id for case in CASES]


def examples_of(contract: str) -> list[dict[str, Any]]:
    return [load_json(path) for path in CONTRACTS.example_paths(contract)]


# --- canaries ---------------------------------------------------------------------------------


def test_the_counterexample_set_is_not_empty() -> None:
    """Without this, every parametrised proof below would pass over an empty list."""
    assert CASES, f"no semantic counterexample discovered under {FIXTURES_DIR}"


def test_every_contract_with_semantic_rules_has_at_least_one_counterexample() -> None:
    covered = {case.contract for case in CASES}
    missing = sorted(set(RULES_BY_CONTRACT) - covered)
    assert missing == [], f"contracts with semantic rules and no counterexample: {missing}"


def test_fixture_directories_name_contracts_that_have_semantic_rules() -> None:
    unknown = sorted({case.contract for case in CASES} - set(RULES_BY_CONTRACT))
    assert unknown == [], f"counterexample directories for unchecked contracts: {unknown}"


def test_every_declared_rule_is_exercised_by_a_counterexample() -> None:
    """A rule nobody breaks on purpose is a rule nobody has seen fire."""
    exercised = {rule for case in CASES for _, rule in case.expected_keys()}
    unexercised = sorted(set(RULES) - exercised)
    stale = sorted(exercised - set(RULES))
    assert unexercised == [], f"rules with no counterexample: {unexercised}"
    assert stale == [], f"counterexamples naming rules that no longer exist: {stale}"


def test_every_rule_belongs_to_exactly_one_contract() -> None:
    """The inventory and the per-contract mapping must describe the same set of rules."""
    mapped = [rule for rules in RULES_BY_CONTRACT.values() for rule in rules]
    assert sorted(mapped) == sorted(RULES), f"mapped {sorted(mapped)} vs declared {sorted(RULES)}"
    assert len(mapped) == len(set(mapped)), "a rule is claimed by two contracts"


def test_every_rule_states_what_it_keeps_unambiguous() -> None:
    for rule, reason in RULES.items():
        assert reason.strip(), f"{rule}: say what the rule keeps unambiguous"


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_case_and_expectation_are_paired(case: SemanticCase) -> None:
    assert case.document_path is not None, f"{case.id}: the index names a case with no document"
    assert case.expectation is not None, f"{case.id}: document has no entry in the index"
    assert case.expectation["proves"].strip(), f"{case.id}: say what the case proves"
    assert case.expected_keys(), f"{case.id}: name at least one expected rule"


def test_expectations_record_no_free_text_violation() -> None:
    """Only ``pointer`` and ``rule`` are stable, exactly as the schema expectations record only
    ``pointer`` and ``keyword``."""
    for index_path in sorted(FIXTURES_DIR.glob(f"*/{EXPECTATIONS_FILENAME}")):
        index = load_json(index_path)
        assert index["contract"] == index_path.parent.name
        for name, case in index["cases"].items():
            for violation in case["violations"]:
                unexpected = sorted(set(violation) - {"pointer", "rule"})
                assert unexpected == [], f"{index_path.parent.name}/{name}: carries {unexpected}"


def test_the_checker_reports_nothing_on_a_document_that_is_unambiguous() -> None:
    """Canary: a checker that reported a violation for everything would make every proof below
    pass for the wrong reason."""
    for contract in CONTRACT_NAMES:
        for document in examples_of(contract):
            assert violations_of(contract, document) == (), contract


def test_the_checker_refuses_a_contract_it_has_no_rules_for() -> None:
    """Returning "no violations" for an unchecked contract is the silent pass this layer exists
    to prevent, so an unknown name raises instead."""
    with pytest.raises(KeyError):
        violations_of("problem", {})


# --- the counterexamples ----------------------------------------------------------------------


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_the_counterexample_satisfies_the_schema_completely(case: SemanticCase) -> None:
    """The load-bearing assertion of this module: the schema has nothing to say about any of
    these documents, so uniqueItems and the closed roots are demonstrably not enough."""
    found = CONTRACTS.validate(case.contract, case.document())
    assert found == (), "\n".join(f"{v.pointer} [{v.keyword}] {v.message}" for v in found)


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_the_counterexample_is_rejected_by_the_semantic_layer(case: SemanticCase) -> None:
    actual = {violation.key for violation in violations_of(case.contract, case.document())}
    assert case.expected_keys() <= actual, (
        f"{case.id}: expected {sorted(case.expected_keys())} within {sorted(actual)}"
    )


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_the_semantic_verdict_is_deterministic(case: SemanticCase) -> None:
    document = case.document()
    assert violations_of(case.contract, document) == violations_of(case.contract, document)


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_the_gate_raises_rather_than_returning_on_an_ambiguous_document(
    case: SemanticCase,
) -> None:
    with pytest.raises(SemanticAmbiguity) as raised:
        require_unambiguous(case.contract, case.document())
    assert case.expected_keys() <= raised.value.keys
    assert raised.value.contract == case.contract


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_the_digest_refuses_an_ambiguous_document_rather_than_producing_a_value(
    case: SemanticCase,
) -> None:
    """The rule stated in both output_digest descriptions, executed."""
    with pytest.raises(SemanticAmbiguity):
        PROJECTIONS[case.contract](case.document())


# --- why failing closed is necessary, not merely tidy ------------------------------------------


def _unguarded_inventory_order(document: dict[str, Any]) -> dict[str, Any]:
    """The inventory ordering with the gate removed, reconstructed to show what it prevents.

    Deliberately a copy of the projection's sort rather than a call into it: the point is what
    the canonical ordering would produce *if* it were allowed to run on an ambiguous document,
    and the real projection refuses to run at all.
    """
    return {
        "sources": sorted((dict(s) for s in document["sources"]), key=itemgetter("source_id")),
        "candidates": sorted((dict(c) for c in document["candidates"]), key=itemgetter("url_key")),
    }


def _unguarded_manifest_order(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "selections": sorted(
            (dict(s) for s in document["selections"]), key=itemgetter("selection_rank")
        ),
        "exclusions": sorted((dict(e) for e in document["exclusions"]), key=itemgetter("reason")),
    }


UNGUARDED = {
    SITE_INVENTORY: _unguarded_inventory_order,
    SAMPLING_MANIFEST: _unguarded_manifest_order,
}

#: ``contract -> {collection -> the member the canonical ordering sorts it by}``. Copied from the
#: projections in ``tests.acquisition.digests`` so the hazard below is demonstrated against the
#: real keys rather than against a plausible guess about them.
SORT_KEYS: dict[str, dict[str, str]] = {
    SITE_INVENTORY: {"sources": "source_id", "candidates": "url_key"},
    SAMPLING_MANIFEST: {"selections": "selection_rank", "exclusions": "reason"},
}

#: ``rule -> (collection, member)`` for the rules whose duplicate lands **on a sort key**. Those
#: are the ones that make the canonical ordering itself depend on input sequence, and they are
#: what the order proof below exercises.
TIE_CREATING_RULES: dict[str, tuple[str, str]] = {
    "unique_source_id": ("sources", "source_id"),
    "unique_candidate_url_key": ("candidates", "url_key"),
    "unique_selection_rank": ("selections", "selection_rank"),
    "unique_exclusion_reason": ("exclusions", "reason"),
}

#: The rules that are **not** about a sort tie, each with the different thing it protects. Stated
#: rather than left implicit: a reader who assumed all six rules existed for the digest would
#: quietly conclude the two below are redundant, and they are not.
#:
#: * ``unique_selected_url_key`` — selections are ordered by ``selection_rank``, so one identity
#:   at two ranks creates no tie at all. What it breaks is that the selection set stops being a
#:   set: the manifest states it selected n pages while covering fewer, and the accounting
#:   identity ``selections + exclusions == the bound population`` double-counts one candidate.
#: * ``dense_selection_rank`` — a gap repeats nothing, so there is no tie either. What it breaks
#:   is that the order authority names a position no selection occupies.
NON_TIE_RULES = ("unique_selected_url_key", "dense_selection_rank")

ORDER_SENSITIVE_CASES = [
    case for case in CASES if {rule for _, rule in case.expected_keys()} & set(TIE_CREATING_RULES)
]
ORDER_SENSITIVE_IDS = [case.id for case in ORDER_SENSITIVE_CASES]


def test_every_rule_is_either_tie_creating_or_named_as_something_else() -> None:
    """Canary: a rule that fell out of both groups would leave this section silently incomplete,
    and a tie-creating rule must actually name a collection the projections sort."""
    classified = set(TIE_CREATING_RULES) | set(NON_TIE_RULES)
    assert classified == set(RULES), f"unclassified {sorted(set(RULES) - classified)}"
    assert not set(TIE_CREATING_RULES) & set(NON_TIE_RULES), "a rule is in both groups"
    for rule, (collection, member) in TIE_CREATING_RULES.items():
        contract = next(c for c, rules in RULES_BY_CONTRACT.items() if rule in rules)
        assert SORT_KEYS[contract][collection] == member, (
            f"{rule}: the projection does not order {collection} by {member}"
        )


def test_every_tie_creating_rule_has_a_counterexample_in_the_order_proof() -> None:
    exercised = {
        rule
        for case in ORDER_SENSITIVE_CASES
        for _, rule in case.expected_keys()
        if rule in TIE_CREATING_RULES
    }
    missing = sorted(set(TIE_CREATING_RULES) - exercised)
    assert missing == [], f"tie-creating rules with no order counterexample: {missing}"


@pytest.mark.parametrize("case", ORDER_SENSITIVE_CASES, ids=ORDER_SENSITIVE_IDS)
def test_an_ambiguous_document_would_digest_differently_under_two_serialisations(
    case: SemanticCase,
) -> None:
    """This is why the gate exists. ``sorted`` is stable, so with the guard removed the canonical
    ordering of an ambiguous document is decided by the sequence it arrived in — two byte
    sequences for the same semantics, and two different digests. Refusing is the only answer that
    keeps the word canonical true."""
    rule = next(r for _, r in case.expected_keys() if r in TIE_CREATING_RULES)
    member, _key = TIE_CREATING_RULES[rule]
    document = case.document()
    swapped = copy.deepcopy(document)
    swapped[member] = list(reversed(swapped[member]))

    unguarded = UNGUARDED[case.contract]
    assert digest_of(unguarded(document)) != digest_of(unguarded(swapped)), (
        f"{case.id}: the unguarded ordering is order-independent here, so this case does not "
        "demonstrate the hazard the gate closes"
    )
    for candidate in (document, swapped):
        with pytest.raises(SemanticAmbiguity):
            PROJECTIONS[case.contract](candidate)


def test_selecting_one_identity_twice_breaks_the_selection_accounting() -> None:
    """What ``unique_selected_url_key`` protects, since it is not a sort tie.

    The registered manifests are checked against the identity ``len(selections) + the exclusion
    counts == the bound population``. A manifest that selects one identity twice satisfies that
    arithmetic while covering one page fewer than it claims — the accounting stops meaning what
    it says, and the selection set stops being a set.
    """
    document = load_json(FIXTURES_DIR / SAMPLING_MANIFEST / "duplicate-selected-url-key.json")
    selected = [entry["url_key"] for entry in document["selections"]]
    assert len(selected) > len(set(selected)), "canary: the fixture selects no identity twice"
    assert CONTRACTS.validate(SAMPLING_MANIFEST, document) == (), "canary: the schema allows it"
    keys = {v.key for v in violations_of(SAMPLING_MANIFEST, document)}
    assert ("/selections/1", "unique_selected_url_key") in keys


# --- the mirror: a valid document is order-independent and digests fine ------------------------


def test_every_registered_example_passes_the_semantic_layer() -> None:
    """A rule the registered examples break would be a rule the repository does not follow."""
    for contract in CONTRACT_NAMES:
        for document in examples_of(contract):
            require_unambiguous(contract, document)


@pytest.mark.parametrize("contract", CONTRACT_NAMES)
def test_reordering_an_unambiguous_document_leaves_its_output_digest_unchanged(
    contract: str,
) -> None:
    """The property the gate protects: with the keys unambiguous, order genuinely does not
    matter, and the digest proves it over every order-independent collection of every example."""
    members = ("sources", "candidates") if contract == SITE_INVENTORY else ("exclusions",)
    reordered = 0
    for document in examples_of(contract):
        baseline = digest_of(PROJECTIONS[contract](document))
        assert baseline == document["output_digest"], document.get("inventory_id")
        for member in members:
            if len(document[member]) < 2:
                continue
            for permutation in itertools.permutations(document[member]):
                candidate = dict(document, **{member: list(permutation)})
                assert digest_of(PROJECTIONS[contract](candidate)) == baseline, member
                reordered += 1
    assert reordered > 0, f"canary: nothing was reordered for {contract}"


def test_reordering_the_selections_of_an_unambiguous_manifest_changes_no_digest() -> None:
    """Selections are order-independent in the array because the ranks carry the order; with the
    ranks unique and dense, every permutation of the array digests identically."""
    permuted = 0
    for document in examples_of(SAMPLING_MANIFEST):
        baseline = digest_of(manifest_output_projection(document))
        for permutation in itertools.permutations(document["selections"]):
            candidate = dict(document, selections=list(permutation))
            assert digest_of(manifest_output_projection(candidate)) == baseline
            permuted += 1
    assert permuted > len(examples_of(SAMPLING_MANIFEST)), "canary: no permutation was exercised"


# --- the violation record itself ---------------------------------------------------------------


def test_a_violation_is_addressed_by_pointer_and_rule_and_carries_no_free_text() -> None:
    """Structural, for the same reason the schema expectations are: free text is what makes an
    expectation go red on a reworded message."""
    violation = SemanticViolation("/selections/1", "unique_selection_rank")
    assert violation.key == ("/selections/1", "unique_selection_rank")
    assert set(json.loads(json.dumps(violation.__dict__))) == {"pointer", "rule"}


def test_the_later_occurrence_is_reported_rather_than_the_first() -> None:
    """The first use of a key is legitimate; the entry that made the document ambiguous is the
    one a reader has to remove."""
    document = load_json(FIXTURES_DIR / SITE_INVENTORY / "duplicate-source-id.json")
    pointers = [v.pointer for v in violations_of(SITE_INVENTORY, document)]
    assert pointers == ["/sources/2"], pointers


def test_an_ambiguity_carries_its_violations_rather_than_a_rendered_message() -> None:
    document = load_json(FIXTURES_DIR / SAMPLING_MANIFEST / "gapped-selection-rank.json")
    with pytest.raises(SemanticAmbiguity) as raised:
        require_unambiguous(SAMPLING_MANIFEST, document)
    assert raised.value.keys == {("/selections", "dense_selection_rank")}
    assert "dense_selection_rank" in str(raised.value)
