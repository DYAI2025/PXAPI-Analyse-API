"""The semantic-key rules JSON Schema cannot state, and the gate that fails closed on them.

Five relationships these two contracts depend on are not expressible in Draft 2020-12. Each is a
statement about *two items of one array*, and the dialect offers exactly one keyword that looks
like it helps — ``uniqueItems`` — which compares **whole items**. Two sources with the same
``source_id`` and different outcomes, two candidates with the same ``url_key`` and different
observed forms, two selections with the same ``url_key`` at different ranks, two selections at
the same rank, two exclusion entries for one reason: every one of those satisfies ``uniqueItems``
and every one of them leaves the document ambiguous.

Ambiguous is the operative word, and it is why this module exists in PXAPI-19.A rather than being
deferred. ``tests.acquisition.digests`` orders each order-independent collection by its semantic
key before digesting it, because a set rendered as an array must not make a digest depend on the
sequence a producer happened to emit. ``sorted`` is stable: when two keys compare equal it keeps
the input order, so a document carrying a duplicate key produces a digest that **does** depend on
input sequence — quietly, with no error, and differently for two serialisations of the same
document. A canonical digest that is not canonical is worse than none, so the projections call
:func:`require_unambiguous` first and refuse to produce a value at all.

Scope. PXAPI-19.A authorises no production validator, so this layer is test code and lives here
rather than under ``src/pxapi``. It is not a second contract: it states rules the schemas already
carry in prose, at the members that carry them, and it is the executable form of those sentences.
**Equivalent producer-side enforcement is mandatory in PXAPI-19.B** — a producer that emits a
duplicate semantic key is emitting a document no consumer can order, and nothing in 19.A stops it
from doing so.

The layer runs *after* schema validation and assumes nothing about a document that failed it: an
item missing the member a rule keys on is not a semantic question but a structural one, and is
left to the schema layer rather than reported twice.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

SITE_INVENTORY = "site-inventory"
SAMPLING_MANIFEST = "sampling-manifest"

#: A sentinel for "this item does not carry the member this rule keys on". ``None`` would be
#: indistinguishable from a JSON null, which no member of either contract admits but which a
#: hand-written fixture could still hold.
_ABSENT = object()


@dataclass(frozen=True)
class SemanticViolation:
    """One broken semantic-key rule, addressed the way a schema violation is.

    ``pointer`` is a JSON pointer into the offending document and ``rule`` is the stable name of
    the rule, never free text: an expectation that recorded a sentence would go red on a reworded
    message, exactly as the invalid-fixture expectations avoid for the same reason.
    """

    pointer: str
    rule: str

    @property
    def key(self) -> tuple[str, str]:
        return self.pointer, self.rule


class SemanticAmbiguity(Exception):
    """A document whose semantic keys leave it without a canonical ordering.

    It carries the violations rather than a rendered message so a caller can assert on the rule
    that fired instead of on how it was phrased.
    """

    def __init__(self, contract: str, violations: Sequence[SemanticViolation]) -> None:
        self.contract = contract
        self.violations: tuple[SemanticViolation, ...] = tuple(violations)
        rendered = ", ".join(f"{v.pointer} [{v.rule}]" for v in self.violations)
        super().__init__(f"{contract}: ambiguous semantic keys: {rendered}")

    @property
    def keys(self) -> set[tuple[str, str]]:
        return {violation.key for violation in self.violations}


# --- the rules --------------------------------------------------------------------------------

#: ``rule name -> what it keeps unambiguous``. The mapping is the inventory of this layer: a
#: coverage test asserts every rule named here is exercised by a counterexample, so a rule added
#: without a proof, or a proof left behind by a deleted rule, is reported rather than absorbed.
RULES: dict[str, str] = {
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

#: ``contract -> the rules that contract is checked against``. Derived from one place so the
#: coverage test and the checkers cannot disagree about which rules exist for which contract.
RULES_BY_CONTRACT: dict[str, tuple[str, ...]] = {
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
    return [
        item.get(member, _ABSENT) if isinstance(item, dict) else _ABSENT  # type: ignore[union-attr]
        for item in items
    ]


def _repeats(
    document: dict[str, Any], collection: str, member: str, rule: str
) -> list[SemanticViolation]:
    """A violation at every index whose key was already used by an earlier index.

    The *later* occurrence is reported, not the first: the first use of a key is legitimate, and
    pointing at the entry that made the document ambiguous is what a reader needs to fix it.
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


def site_inventory_violations(document: dict[str, Any]) -> tuple[SemanticViolation, ...]:
    """Every semantic-key rule ``site-inventory.v1`` carries, checked over one document."""
    found: list[SemanticViolation] = []
    found += _repeats(document, "sources", "source_id", "unique_source_id")
    found += _repeats(document, "candidates", "url_key", "unique_candidate_url_key")
    return tuple(found)


def sampling_manifest_violations(document: dict[str, Any]) -> tuple[SemanticViolation, ...]:
    """Every semantic-key rule ``sampling-manifest.v1`` carries, checked over one document."""
    found: list[SemanticViolation] = []
    found += _repeats(document, "selections", "url_key", "unique_selected_url_key")
    found += _repeats(document, "selections", "selection_rank", "unique_selection_rank")
    found += _dense_ranks(document)
    found += _repeats(document, "exclusions", "reason", "unique_exclusion_reason")
    return tuple(found)


def _dense_ranks(document: dict[str, Any]) -> list[SemanticViolation]:
    """The ranks of one manifest must be exactly ``1..n``.

    A duplicate rank already fails ``unique_selection_rank``; density is reported separately so a
    gap — which leaves the order authority pointing at an unoccupied position without any rank
    being repeated — is a counterexample in its own right rather than a side effect of another
    rule. The violation is addressed at the array, because a gap belongs to the sequence and not
    to any one selection in it.
    """
    selections = document.get("selections")
    if not isinstance(selections, list) or not selections:
        return []
    ranks = [value for value in _keys_at(selections, "selection_rank") if value is not _ABSENT]
    if len(ranks) != len(selections):
        return []
    if sorted(ranks) == list(range(1, len(ranks) + 1)):
        return []
    return [SemanticViolation("/selections", "dense_selection_rank")]


CHECKERS = {
    SITE_INVENTORY: site_inventory_violations,
    SAMPLING_MANIFEST: sampling_manifest_violations,
}


def violations_of(contract: str, document: dict[str, Any]) -> tuple[SemanticViolation, ...]:
    """Every semantic-key violation of ``document`` under ``contract``.

    An unknown contract raises rather than returning an empty tuple: silently reporting "no
    violations" for a contract nobody checks is the failure mode this layer exists to prevent.
    """
    if contract not in CHECKERS:
        raise KeyError(f"no semantic-key rules are defined for contract {contract!r}")
    return CHECKERS[contract](document)


def require_unambiguous(contract: str, document: dict[str, Any]) -> None:
    """Fail closed: raise :class:`SemanticAmbiguity` unless the document's keys are unambiguous.

    Called by the digest projections before they order anything, so a document a producer could
    serialise two ways never receives a digest that depends on which way it chose.
    """
    found = violations_of(contract, document)
    if found:
        raise SemanticAmbiguity(contract, found)
