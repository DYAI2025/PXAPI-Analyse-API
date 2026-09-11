"""The acquisition invariants JSON Schema cannot state, enforced where documents are produced.

PXAPI-19.A stated five relationships the two acquisition contracts depend on and that Draft
2020-12 cannot express, wrote them into the schemas as prose at the members that carry them,
and made them executable as *test* code — because 19.A shipped no producer. Every one of those
sentences ends the same way: **equivalent producer-side enforcement is mandatory in
PXAPI-19.B**. This module is that enforcement.

It is deliberately two layers, because they answer two different questions.

**The contract-semantic layer** is exactly the 19.A rule set, no more and no less. A document
breaking one of these has no canonical ordering at all: the digest projections sort each
order-independent collection by its semantic key, ``sorted`` is stable, and a repeated key
therefore leaves the tie to be broken by whatever sequence a producer happened to emit — so
two serialisations of one document would receive two different digests, silently. A canonical
digest that is not canonical is worse than none, so the projections call
:func:`require_unambiguous` and refuse to produce a value at all.
``tests/domain/test_acquisition_semantics.py`` asserts this layer agrees with the 19.A
reference in ``tests/acquisition/semantics.py`` on every document either of them is given, so
the producer and the contract statement cannot drift into two different rule sets.

**The producer layer** is additional and is *ours*. These are not contract rules and are never
applied to a document somebody else wrote: they are the guarantees this producer makes about
what it emits — that the seed exists and is the origin, that a selection names a candidate the
bound inventory actually offered, that the counts add up. They exist because a producer is the
only place they can be checked, and because a wrong document that satisfies its schema is
exactly the failure the whole contract-first approach is meant to make impossible.

Both layers fail **closed**: they raise rather than return a repaired document. A producer that
patched its own output would be deciding what the analysis found, which is not its job.

Standard library only. The domain ring imports no third-party distribution at all.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Final

SITE_INVENTORY: Final = "site-inventory"
SAMPLING_MANIFEST: Final = "sampling-manifest"

#: A sentinel for "this item does not carry the member this rule keys on". ``None`` would be
#: indistinguishable from a JSON null, which no member of either contract admits.
_ABSENT: Final = object()

#: The source outcomes under which a non-zero admitted count is possible at all. Restated from
#: the contract rather than imported from the discovery vocabulary, because this module checks
#: *documents* and must work on one that names an outcome no producer of ours emits.
_ADMITTING_OUTCOMES: Final[frozenset[str]] = frozenset({"USED", "BUDGET_EXHAUSTED", "TIMEOUT"})


@dataclass(frozen=True)
class SemanticViolation:
    """One broken invariant, addressed the way a schema violation is.

    ``pointer`` is a JSON pointer into the offending document and ``rule`` is the stable name of
    the rule, never free text: an expectation recording a sentence would go red on a reworded
    message, which is the same reason the invalid-fixture expectations record keywords.
    """

    pointer: str
    rule: str

    @property
    def key(self) -> tuple[str, str]:
        return self.pointer, self.rule


class SemanticAmbiguity(Exception):
    """A document whose semantic keys leave it without a canonical ordering."""

    def __init__(self, contract: str, violations: Sequence[SemanticViolation]) -> None:
        self.contract = contract
        self.violations: tuple[SemanticViolation, ...] = tuple(violations)
        rendered = ", ".join(f"{v.pointer} [{v.rule}]" for v in self.violations)
        super().__init__(f"{contract}: ambiguous semantic keys: {rendered}")

    @property
    def keys(self) -> set[tuple[str, str]]:
        return {violation.key for violation in self.violations}


class ProducerInvariantViolated(Exception):
    """This producer built a document it is not allowed to emit.

    It names a defect in *this service* and never anything about the analysed website, exactly
    as the registry's ``CANONICAL_OUTPUT_INVALID`` problem code does. The offending document is
    withheld rather than returned, because emitting it would publish a claim no consumer can
    read correctly.
    """

    def __init__(self, contract: str, violations: Sequence[SemanticViolation]) -> None:
        self.contract = contract
        self.violations: tuple[SemanticViolation, ...] = tuple(violations)
        rendered = ", ".join(f"{v.pointer} [{v.rule}]" for v in self.violations)
        super().__init__(f"{contract}: producer invariant violated: {rendered}")

    @property
    def keys(self) -> set[tuple[str, str]]:
        return {violation.key for violation in self.violations}


# --- the contract-semantic rules ---------------------------------------------------------------

#: ``rule name -> what it keeps unambiguous``. The names are the 19.A names, unchanged: an
#: equivalence test compares this layer's verdicts with the 19.A reference rule for rule, and a
#: rename here would make that comparison meaningless rather than red.
CONTRACT_RULES: Final[dict[str, str]] = {
    "unique_source_id": (
        "One attempted discovery source is reported once, so a candidate's provenance resolves "
        "to exactly one outcome and the canonical ordering of sources has no tie to break."
    ),
    "unique_candidate_url_key": (
        "One canonical identity appears once in the candidate population, because observations "
        "that share an identity aggregate onto one candidate rather than becoming several."
    ),
    "unique_selected_url_key": (
        "One identity is selected once per manifest, so the selection set is a set and the "
        "canonical ordering by identity has no tie to break."
    ),
    "unique_selection_rank": (
        "One rank is occupied by one selection, so the order authority names a single position."
    ),
    "dense_selection_rank": (
        "The ranks of one manifest are exactly 1..n, so the order authority points at no "
        "position that nothing occupies."
    ),
    "unique_exclusion_reason": (
        "One exclusion reason is summarised once, so a reader never has to add two partial "
        "counts and the canonical ordering by reason has no tie to break."
    ),
}

CONTRACT_RULES_BY_CONTRACT: Final[dict[str, tuple[str, ...]]] = {
    SITE_INVENTORY: ("unique_source_id", "unique_candidate_url_key"),
    SAMPLING_MANIFEST: (
        "unique_selected_url_key",
        "unique_selection_rank",
        "dense_selection_rank",
        "unique_exclusion_reason",
    ),
}


def _keys_at(items: Iterable[Any], member: str) -> list[Any]:
    """The value of ``member`` in each item, with ``_ABSENT`` where the item does not carry it."""
    return [item.get(member, _ABSENT) if isinstance(item, dict) else _ABSENT for item in items]


def _repeats(
    document: dict[str, Any], collection: str, member: str, rule: str
) -> list[SemanticViolation]:
    """A violation at every index whose key was already used by an earlier index.

    The *later* occurrence is reported: the first use of a key is legitimate, and pointing at
    the entry that made the document ambiguous is what a reader needs in order to fix it.
    """
    items = document.get(collection)
    if not isinstance(items, list):
        return []
    seen: list[Any] = []
    found: list[SemanticViolation] = []
    for index, value in enumerate(_keys_at(items, member)):
        if value is _ABSENT:
            continue
        if value in seen:
            found.append(SemanticViolation(f"/{collection}/{index}", rule))
        else:
            seen.append(value)
    return found


def _dense_ranks(document: dict[str, Any]) -> list[SemanticViolation]:
    """The ranks of one manifest must be exactly ``1..n``.

    A duplicate rank already fails ``unique_selection_rank``; density is reported separately so
    a gap — which leaves the order authority pointing at an unoccupied position without any
    rank being repeated — is a counterexample in its own right. The violation is addressed at
    the array, because a gap belongs to the sequence and not to any one selection in it.

    A rank that is absent, null or not a whole number is a *structural* defect the schema layer
    reports, and density is undefined over it. Filtering on the type matters: ``sorted`` raises
    on a list mixing ``None`` with integers, and a checker that crashes reports nothing at all,
    which is the opposite of failing closed. ``bool`` is excluded because it is an ``int``
    subclass in Python and ``True`` would otherwise pass for rank 1.
    """
    selections = document.get("selections")
    if not isinstance(selections, list) or not selections:
        return []
    ranks = [
        value
        for value in _keys_at(selections, "selection_rank")
        if isinstance(value, int) and not isinstance(value, bool)
    ]
    if len(ranks) != len(selections):
        return []
    if sorted(ranks) == list(range(1, len(ranks) + 1)):
        return []
    return [SemanticViolation("/selections", "dense_selection_rank")]


def site_inventory_violations(document: dict[str, Any]) -> tuple[SemanticViolation, ...]:
    """Every contract-semantic rule ``site-inventory.v1`` carries, checked over one document."""
    found: list[SemanticViolation] = []
    found += _repeats(document, "sources", "source_id", "unique_source_id")
    found += _repeats(document, "candidates", "url_key", "unique_candidate_url_key")
    return tuple(found)


def sampling_manifest_violations(document: dict[str, Any]) -> tuple[SemanticViolation, ...]:
    """Every contract-semantic rule ``sampling-manifest.v1`` carries, over one document."""
    found: list[SemanticViolation] = []
    found += _repeats(document, "selections", "url_key", "unique_selected_url_key")
    found += _repeats(document, "selections", "selection_rank", "unique_selection_rank")
    found += _dense_ranks(document)
    found += _repeats(document, "exclusions", "reason", "unique_exclusion_reason")
    return tuple(found)


_CONTRACT_CHECKERS: Final = {
    SITE_INVENTORY: site_inventory_violations,
    SAMPLING_MANIFEST: sampling_manifest_violations,
}


def violations_of(contract: str, document: dict[str, Any]) -> tuple[SemanticViolation, ...]:
    """Every contract-semantic violation of ``document``.

    An unknown contract raises rather than returning an empty tuple: silently reporting "no
    violations" for a contract nobody checks is the failure mode this layer exists to prevent.
    """
    if contract not in _CONTRACT_CHECKERS:
        raise KeyError(f"no semantic rules are defined for contract {contract!r}")
    return _CONTRACT_CHECKERS[contract](document)


def require_unambiguous(contract: str, document: dict[str, Any]) -> None:
    """Fail closed: raise unless the document's semantic keys leave it one canonical order.

    Called by the digest projections before they order anything, so a document a producer could
    serialise two ways never receives a digest that depends on which way it chose.
    """
    found = violations_of(contract, document)
    if found:
        raise SemanticAmbiguity(contract, found)


# --- the producer invariants ---------------------------------------------------------------

#: ``rule name -> the guarantee this producer makes``. These are **not** contract rules. A
#: document from elsewhere that breaks one is not thereby invalid; a document *we* built that
#: breaks one is withheld, because we would be publishing something we cannot stand behind.
PRODUCER_RULES: Final[dict[str, str]] = {
    "seed_candidate_present": (
        "An emitted inventory carries the canonical target seed: a candidate whose url_key is "
        "the target origin and whose provenance names CANONICAL_SEED. D-PXAPI19-PO-006: an "
        "inventory exists only after the origin was established."
    ),
    "seed_candidate_eligible": (
        "The canonical target seed is a technically admissible target. A seed this run may not "
        "fetch is a bootstrap that did not succeed, and no inventory follows from it."
    ),
    "admitting_outcome_for_contributed_source": (
        "A source that contributed a candidate reports an outcome under which admission was "
        "possible, so no absent, malformed, refused or failed source can claim to have "
        "contributed pages."
    ),
    "source_declared_for_every_provenance": (
        "Every source a candidate names is a source the inventory reports an outcome for, so "
        "provenance always resolves to exactly one attempt."
    ),
    "candidate_count_matches_provenance": (
        "A source's admitted count is the number of candidates naming it, so the summary and "
        "the population cannot state two different things about one source."
    ),
    "selection_is_an_inventory_candidate": (
        "Every selected identity is a candidate of the bound inventory, so a manifest can "
        "never name a page the population it cites never offered."
    ),
    "selection_is_eligible_in_inventory": (
        "Every selected identity was ELIGIBLE in the bound inventory, so a technical exclusion "
        "recorded by discovery cannot be quietly reversed by selection."
    ),
    "every_selection_carries_a_stratum": (
        "Every selection names the bucket it was counted under, using the neutral UNCLASSIFIED "
        "token when the classifier placed none."
    ),
    "exclusions_account_for_the_remainder": (
        "The selections and the exclusion counts together account for every candidate of the "
        "bound inventory exactly once, so a page can neither vanish from the summary nor be "
        "counted twice."
    ),
    "incompleteness_matches_completeness": (
        "An incomplete selection names the technical limitation that stopped it, and a "
        "complete one names none, so neither state can exist as a bare assertion."
    ),
    "budget_cause_declares_its_budget": (
        "A selection stopped by a declared budget declares that budget, so the bound can be "
        "read rather than merely asserted."
    ),
    "census_never_emits_a_sample": (
        "While the census-to-sampling threshold is MISSING, the executable policy is CENSUS "
        "only: STRATIFIED_SAMPLE is contract vocabulary and not a producer capability."
    ),
}

#: The one selection mode this producer may emit. The other token exists in the contract so a
#: manifest can *say* which method was used; it is not a capability until a benchmark-based
#: threshold exists, and C-PXAPI-005 keeps that threshold explicitly MISSING.
EXECUTABLE_MODE: Final = "CENSUS"

#: The incompleteness cause that drags a declared budget with it.
BUDGET_CAUSE: Final = "SELECTION_BUDGET_EXHAUSTED"


def _state_of(candidate: dict[str, Any]) -> Any:
    """A candidate's eligibility state, or ``_ABSENT`` when the member is not an object."""
    eligibility = candidate.get("eligibility")
    return eligibility.get("state", _ABSENT) if isinstance(eligibility, dict) else _ABSENT


def inventory_producer_violations(document: dict[str, Any]) -> tuple[SemanticViolation, ...]:
    """Every producer guarantee ``site-inventory.v1`` output must satisfy."""
    found: list[SemanticViolation] = []
    candidates = document.get("candidates")
    sources = document.get("sources")
    if not isinstance(candidates, list) or not isinstance(sources, list):
        return ()

    origin = document.get("target_origin")
    seed = next((c for c in candidates if isinstance(c, dict) and c.get("url_key") == origin), None)
    if seed is None or "CANONICAL_SEED" not in seed.get("provenance", []):
        found.append(SemanticViolation("/candidates", "seed_candidate_present"))
    elif _state_of(seed) != "ELIGIBLE":
        found.append(SemanticViolation("/candidates", "seed_candidate_eligible"))

    declared: dict[str, Any] = {}
    for source in sources:
        if isinstance(source, dict) and isinstance(source.get("source_id"), str):
            declared[source["source_id"]] = source

    contributed: dict[str, int] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        for name in candidate.get("provenance", []):
            contributed[name] = contributed.get(name, 0) + 1

    for name in sorted(contributed):
        if name not in declared:
            found.append(SemanticViolation("/candidates", "source_declared_for_every_provenance"))
            continue
        index = sources.index(declared[name])
        if declared[name].get("outcome") not in _ADMITTING_OUTCOMES:
            found.append(
                SemanticViolation(f"/sources/{index}", "admitting_outcome_for_contributed_source")
            )

    for index, source in enumerate(sources):
        if not isinstance(source, dict) or not isinstance(source.get("source_id"), str):
            continue
        expected = contributed.get(source["source_id"], 0)
        if source.get("candidate_count") != expected:
            found.append(
                SemanticViolation(f"/sources/{index}", "candidate_count_matches_provenance")
            )
    return tuple(found)


def manifest_producer_violations(
    document: dict[str, Any], inventory: dict[str, Any]
) -> tuple[SemanticViolation, ...]:
    """Every producer guarantee ``sampling-manifest.v1`` output must satisfy.

    The bound inventory is required rather than optional: half of these guarantees are about
    the relationship between the two documents, and a check that silently skipped them when
    the inventory was not to hand would be an exemption nobody asked for.
    """
    found: list[SemanticViolation] = []
    selections = document.get("selections")
    exclusions = document.get("exclusions")
    candidates = inventory.get("candidates")
    if (
        not isinstance(selections, list)
        or not isinstance(exclusions, list)
        or not isinstance(candidates, list)
    ):
        return ()

    if document.get("mode") != EXECUTABLE_MODE:
        found.append(SemanticViolation("/mode", "census_never_emits_a_sample"))

    eligible_keys = {
        c["url_key"]
        for c in candidates
        if isinstance(c, dict) and isinstance(c.get("url_key"), str) and _state_of(c) == "ELIGIBLE"
    }
    all_keys = {
        c["url_key"]
        for c in candidates
        if isinstance(c, dict) and isinstance(c.get("url_key"), str)
    }

    for index, selection in enumerate(selections):
        if not isinstance(selection, dict):
            continue
        key = selection.get("url_key")
        if key not in all_keys:
            found.append(
                SemanticViolation(f"/selections/{index}", "selection_is_an_inventory_candidate")
            )
        elif key not in eligible_keys:
            found.append(
                SemanticViolation(f"/selections/{index}", "selection_is_eligible_in_inventory")
            )
        stratum = selection.get("stratum")
        if not isinstance(stratum, str) or not stratum:
            found.append(
                SemanticViolation(f"/selections/{index}", "every_selection_carries_a_stratum")
            )

    counted = len(selections) + sum(
        entry.get("candidate_count", 0)
        for entry in exclusions
        if isinstance(entry, dict) and isinstance(entry.get("candidate_count"), int)
    )
    if counted != len(all_keys):
        found.append(SemanticViolation("/exclusions", "exclusions_account_for_the_remainder"))

    complete = document.get("selection_complete")
    incompleteness = document.get("incompleteness")
    cause = incompleteness.get("cause") if isinstance(incompleteness, dict) else None
    if complete is False and cause is None:
        found.append(SemanticViolation("/incompleteness", "incompleteness_matches_completeness"))
    if complete is True and "incompleteness" in document:
        found.append(SemanticViolation("/incompleteness", "incompleteness_matches_completeness"))
    if cause == BUDGET_CAUSE and not document.get("budgets"):
        found.append(SemanticViolation("/budgets", "budget_cause_declares_its_budget"))
    return tuple(found)


def require_emittable_inventory(document: dict[str, Any]) -> None:
    """Fail closed on an inventory this producer may not emit."""
    require_unambiguous(SITE_INVENTORY, document)
    found = inventory_producer_violations(document)
    if found:
        raise ProducerInvariantViolated(SITE_INVENTORY, found)


def require_emittable_manifest(document: dict[str, Any], inventory: dict[str, Any]) -> None:
    """Fail closed on a manifest this producer may not emit."""
    require_unambiguous(SAMPLING_MANIFEST, document)
    found = manifest_producer_violations(document, inventory)
    if found:
        raise ProducerInvariantViolated(SAMPLING_MANIFEST, found)
