"""The deterministic selection policy: which candidates one run sets out to analyse, and why.

Selection is Pixelkiez methodology and never provider policy (D-PXAPI-007). This module is that
methodology at its first executable version, and it is deliberately the smallest policy the
accepted architecture allows: **census first** (D-PXAPI-008). Every eligible candidate of the
bound inventory is selected, in one deterministic order, until a declared budget of ours says
stop.

What it deliberately does not do matters as much.

**It never emits ``STRATIFIED_SAMPLE``.** The contract carries that token so a manifest can say
which method was used; its presence is not a claim that a benchmark-authorised sample can be
produced. The census-to-sampling threshold is ``MISSING`` (C-PXAPI-005, AD-004), so this module
contains no number that decides between the two methods and no code path that could select the
other one. A population of any size is a census here — a large one is a *bounded* census.

**A budget is not a threshold.** ``max_selected_pages`` is a ceiling on how much work one run
may do. Reaching it leaves the mode ``CENSUS``, records ``selection_complete`` as false with the
structured cause ``SELECTION_BUDGET_EXHAUSTED``, and counts the candidates it left out under
that exclusion reason. It never switches the method, and it is never a property of the site.

**The order carries no judgement.** The seed is rank 1 because it is the page the run was
pointed at, and every other eligible candidate follows in ascending order of its canonical
identity. Lexicographic order is chosen *because* it means nothing: it cannot encode relevance,
priority or quality, and it is total and reproducible from the identities alone.

Standard library only. The domain ring imports no third-party distribution at all.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from pxapi.domain.page_classification import UNCLASSIFIED
from pxapi.domain.site_discovery import Candidate

#: The policy this module implements, and its version. Both travel with every manifest: two
#: selections over one inventory are comparable only when the policy and the version agree.
POLICY_ID: Final = "CENSUS_FIRST_DETERMINISTIC"
POLICY_VERSION: Final = "1.0.0"

#: The only mode this policy emits.
MODE_CENSUS: Final = "CENSUS"

#: Why a candidate was taken, in the contract's closed vocabulary.
REASON_SEED: Final = "SEED"
REASON_CENSUS: Final = "CENSUS"

#: Why candidates were not taken, in the contract's closed vocabulary.
EXCLUDED_INELIGIBLE: Final = "INELIGIBLE_IN_INVENTORY"
EXCLUDED_BUDGET: Final = "SELECTION_BUDGET_EXHAUSTED"

#: The structured cause an incomplete selection names.
CAUSE_BUDGET: Final = "SELECTION_BUDGET_EXHAUSTED"


@dataclass(frozen=True)
class SelectionBudgets:
    """The decision-relevant bounds a selection runs under.

    Only what the contract can carry is representable: every bound is a whole number of at
    least one, because a floating-point bound could not be digested deterministically and a
    bound of zero would forbid even the seed.
    """

    max_selected_pages: int | None = None

    def __post_init__(self) -> None:
        value = self.max_selected_pages
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise ValueError("max_selected_pages must be a whole number")
        if value is not None and value < 1:
            raise ValueError("max_selected_pages must be at least 1")

    def declared(self) -> dict[str, int]:
        """The declared bounds, as the manifest's ``budgets`` member carries them."""
        return (
            {}
            if self.max_selected_pages is None
            else {"max_selected_pages": self.max_selected_pages}
        )


@dataclass(frozen=True)
class Selection:
    """One selected page, its deterministic rank, why it was taken and where it was counted."""

    url_key: str
    rank: int
    reason: str
    stratum: str


@dataclass(frozen=True)
class SelectionPlan:
    """The whole outcome of one run of the policy over one inventory."""

    mode: str
    selection_complete: bool
    incompleteness_cause: str | None
    selections: tuple[Selection, ...]
    #: ``(reason, candidate_count)`` pairs, sorted by reason, each reason at most once.
    exclusions: tuple[tuple[str, int], ...]
    budgets: SelectionBudgets


def plan_census(
    candidates: Iterable[Candidate], target_origin: str, budgets: SelectionBudgets
) -> SelectionPlan:
    """Select every eligible candidate, seed first, until a declared budget is reached.

    Raises ``ValueError`` when the inventory offers no eligible seed. That is not a selection
    outcome at all: an inventory exists only once the origin was established, and its seed is
    the page the run was pointed at, so a population without one is a producer defect that
    must surface rather than be planned around.
    """
    population = tuple(candidates)
    eligible = [c for c in population if c.is_eligible]
    ineligible = len(population) - len(eligible)

    seed = next((c for c in eligible if c.url_key == target_origin), None)
    if seed is None:
        raise ValueError("the bound inventory offers no eligible canonical target seed")

    ordered = [seed, *sorted((c for c in eligible if c is not seed), key=lambda c: c.url_key)]

    ceiling = budgets.max_selected_pages
    taken = ordered if ceiling is None else ordered[:ceiling]
    left_by_budget = len(ordered) - len(taken)

    selections = tuple(
        Selection(
            url_key=candidate.url_key,
            rank=index,
            reason=REASON_SEED if candidate is seed else REASON_CENSUS,
            # A candidate the classifier placed nowhere is counted under the neutral bucket the
            # contract names. It is not a lower rank and not a reason to weight it differently.
            stratum=candidate.page_type or UNCLASSIFIED,
        )
        for index, candidate in enumerate(taken, start=1)
    )

    exclusions: list[tuple[str, int]] = []
    if ineligible:
        exclusions.append((EXCLUDED_INELIGIBLE, ineligible))
    if left_by_budget:
        exclusions.append((EXCLUDED_BUDGET, left_by_budget))

    complete = left_by_budget == 0
    return SelectionPlan(
        mode=MODE_CENSUS,
        selection_complete=complete,
        incompleteness_cause=None if complete else CAUSE_BUDGET,
        selections=selections,
        exclusions=tuple(sorted(exclusions)),
        budgets=budgets,
    )
