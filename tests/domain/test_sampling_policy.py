"""The CENSUS policy: seed first, every eligible page after, bounded only by a declared budget.

Two claims are proved here as properties rather than as examples, because examples cannot
prove an absence. The policy emits ``CENSUS`` for every population size tried, bounded or not,
so no size switches the method; and the module carries no number that could be a
census-to-sampling threshold at all, so none can hide in it.
"""

from __future__ import annotations

import ast
import random
from pathlib import Path

import pytest

from pxapi.domain import sampling_policy
from pxapi.domain.page_classification import UNCLASSIFIED
from pxapi.domain.sampling_policy import SelectionBudgets, plan_census
from pxapi.domain.site_discovery import Candidate, Eligibility, ExclusionReason

ORIGIN = "https://example.com/"


def candidate(key: str, *, eligible: bool = True, page_type: str | None = None) -> Candidate:
    return Candidate(
        url_key=key,
        observed_forms=(key,),
        provenance=("CANONICAL_SEED",) if key == ORIGIN else ("SITEMAP",),
        eligibility=Eligibility.ELIGIBLE if eligible else Eligibility.EXCLUDED,
        exclusion_reason=None if eligible else ExclusionReason.NON_PAGE_RESOURCE,
        page_type=page_type,
    )


POPULATION = (
    candidate(ORIGIN, page_type="HOMEPAGE"),
    candidate(ORIGIN + "referenzen", page_type="PROOF"),
    candidate(ORIGIN + "kontakt", page_type="CONTACT"),
    candidate(ORIGIN + "seite-x"),
    candidate(ORIGIN + "broschuere.pdf", eligible=False),
    candidate(ORIGIN + "leistungen", page_type="OFFER"),
)


def test_the_seed_is_rank_one_and_every_other_eligible_page_follows_by_identity() -> None:
    plan = plan_census(POPULATION, ORIGIN, SelectionBudgets())
    assert [(s.rank, s.url_key, s.reason) for s in plan.selections] == [
        (1, ORIGIN, "SEED"),
        (2, ORIGIN + "kontakt", "CENSUS"),
        (3, ORIGIN + "leistungen", "CENSUS"),
        (4, ORIGIN + "referenzen", "CENSUS"),
        (5, ORIGIN + "seite-x", "CENSUS"),
    ]


def test_ranks_are_dense_and_unique_and_identities_are_selected_once() -> None:
    plan = plan_census(POPULATION, ORIGIN, SelectionBudgets())
    ranks = [s.rank for s in plan.selections]
    keys = [s.url_key for s in plan.selections]
    assert sorted(ranks) == list(range(1, len(ranks) + 1))
    assert len(set(keys)) == len(keys)


def test_every_selection_carries_a_stratum_and_an_unplaced_page_the_neutral_one() -> None:
    plan = plan_census(POPULATION, ORIGIN, SelectionBudgets())
    strata = {s.url_key: s.stratum for s in plan.selections}
    assert all(strata.values())
    assert strata[ORIGIN + "seite-x"] == UNCLASSIFIED


def test_an_unbounded_census_is_complete_and_counts_only_the_ineligible() -> None:
    plan = plan_census(POPULATION, ORIGIN, SelectionBudgets())
    assert plan.mode == "CENSUS"
    assert plan.selection_complete is True
    assert plan.incompleteness_cause is None
    assert plan.exclusions == (("INELIGIBLE_IN_INVENTORY", 1),)


def test_a_budget_bounds_the_census_and_says_so_without_changing_the_method() -> None:
    plan = plan_census(POPULATION, ORIGIN, SelectionBudgets(max_selected_pages=2))
    assert plan.mode == "CENSUS"
    assert plan.selection_complete is False
    assert plan.incompleteness_cause == "SELECTION_BUDGET_EXHAUSTED"
    assert plan.budgets.declared() == {"max_selected_pages": 2}
    assert [s.url_key for s in plan.selections] == [ORIGIN, ORIGIN + "kontakt"]
    assert plan.exclusions == (
        ("INELIGIBLE_IN_INVENTORY", 1),
        ("SELECTION_BUDGET_EXHAUSTED", 3),
    )


def test_selections_and_exclusions_account_for_every_candidate_exactly_once() -> None:
    for ceiling in (None, 1, 2, 3, 5, 100):
        plan = plan_census(POPULATION, ORIGIN, SelectionBudgets(max_selected_pages=ceiling))
        counted = len(plan.selections) + sum(count for _, count in plan.exclusions)
        assert counted == len(POPULATION), ceiling


def test_a_budget_of_one_still_takes_the_seed() -> None:
    plan = plan_census(POPULATION, ORIGIN, SelectionBudgets(max_selected_pages=1))
    assert [s.url_key for s in plan.selections] == [ORIGIN]


def test_the_plan_does_not_depend_on_the_order_the_population_arrived_in() -> None:
    reference = plan_census(POPULATION, ORIGIN, SelectionBudgets(max_selected_pages=3))
    shuffler = random.Random(19)
    for _ in range(20):
        shuffled = list(POPULATION)
        shuffler.shuffle(shuffled)
        assert plan_census(shuffled, ORIGIN, SelectionBudgets(max_selected_pages=3)) == reference


def test_exclusion_reasons_are_unique_and_sorted() -> None:
    plan = plan_census(POPULATION, ORIGIN, SelectionBudgets(max_selected_pages=2))
    reasons = [reason for reason, _ in plan.exclusions]
    assert reasons == sorted(set(reasons))


def test_a_population_without_an_eligible_seed_is_not_planned_around() -> None:
    without_seed = tuple(c for c in POPULATION if c.url_key != ORIGIN)
    with pytest.raises(ValueError, match="seed"):
        plan_census(without_seed, ORIGIN, SelectionBudgets())
    excluded_seed = (candidate(ORIGIN, eligible=False), *without_seed)
    with pytest.raises(ValueError, match="seed"):
        plan_census(excluded_seed, ORIGIN, SelectionBudgets())


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "2"])
def test_a_budget_the_contract_could_not_carry_is_refused(value: object) -> None:
    with pytest.raises(ValueError):
        SelectionBudgets(max_selected_pages=value)  # type: ignore[arg-type]


# --- no threshold, no sample ------------------------------------------------------------------


@pytest.mark.parametrize("size", [1, 2, 25, 26, 1000, 10000])
@pytest.mark.parametrize("ceiling", [None, 25])
def test_no_population_size_switches_the_method(size: int, ceiling: int | None) -> None:
    """The threshold is MISSING: every size is a census, a large one merely a bounded one."""
    population = [candidate(ORIGIN, page_type="HOMEPAGE")] + [
        candidate(f"{ORIGIN}p{index:05d}") for index in range(size - 1)
    ]
    plan = plan_census(population, ORIGIN, SelectionBudgets(max_selected_pages=ceiling))
    assert plan.mode == "CENSUS"
    assert {s.reason for s in plan.selections} <= {"SEED", "CENSUS"}
    assert plan.selection_complete is (ceiling is None or size <= ceiling)


def _code_strings_and_numbers(source: str) -> tuple[set[str], set[object]]:
    """Every string and number literal in ``source`` that is code, docstrings excluded."""
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr):
            value = body[0].value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                docstrings.add(id(value))
    strings: set[str] = set()
    numbers: set[object] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and id(node) not in docstrings:
            if isinstance(node.value, str):
                strings.add(node.value)
            elif isinstance(node.value, int | float) and not isinstance(node.value, bool):
                numbers.add(node.value)
    return strings, numbers


POLICY_SOURCE = Path(sampling_policy.__file__).read_text(encoding="utf-8")


def test_the_policy_module_carries_no_number_that_could_be_a_threshold() -> None:
    """Rank 1 and a zero comparison are the only numbers the policy needs, and all it has."""
    _, numbers = _code_strings_and_numbers(POLICY_SOURCE)
    assert numbers <= {0, 1}, numbers


def test_the_policy_module_can_name_no_sampling_mode_but_census() -> None:
    strings, _ = _code_strings_and_numbers(POLICY_SOURCE)
    assert "STRATIFIED_SAMPLE" not in strings
    assert "STRATUM_QUOTA" not in strings
    assert sampling_policy.MODE_CENSUS == "CENSUS"


def test_the_literal_scanner_finds_a_planted_mode_and_a_planted_threshold() -> None:
    """Canary: the two scans above are proved to see what they exist to forbid."""
    planted = (
        '"""Doc mentioning STRATIFIED_SAMPLE is fine."""\nMODE = "STRATIFIED_SAMPLE"\nT = 500\n'
    )
    strings, numbers = _code_strings_and_numbers(planted)
    assert "STRATIFIED_SAMPLE" in strings
    assert 500 in numbers
    docstring_only, _ = _code_strings_and_numbers('"""STRATIFIED_SAMPLE"""\n')
    assert "STRATIFIED_SAMPLE" not in docstring_only
