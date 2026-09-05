"""Every closed vocabulary in the registry is pinned as a whole set, not one token at a time.

An invalid fixture proves that *one* token is rejected. It never pins the *set*: widening a
closed enum with any token no fixture happens to use leaves every fixture green, because each
fixture only ever asserts about the value it carries. That is not a theory about this suite —
it was measured on this tree with every other test of this slice already in place. A third
``scan_mode`` (``AUTHENTICATED_DEEP``), a fifth stage ``status`` (``PAUSED``) and a fourth
member of the run state's terminal condition (``CREATED``) each left ``pytest`` at 449 passed,
rc 0. The stage-status and stage-terminal widenings were caught only when the added token
happened to collide with the token a fixture already used, which is luck, not a gate.

This module closes that gap in two ways. It states each closed vocabulary once and in full,
and — the part that still holds when a later slice adds a contract — it fails when a closed
vocabulary appears anywhere in the registry that nobody has pinned. Where a vocabulary has a
source of truth in the Domain it is derived from it rather than copied, so a pin here cannot
drift from the code it pins; where a generic registry rule already owns a vocabulary, this
module names that rule instead of restating the fact a second time.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from pxapi.domain.run_state import TERMINAL_STATES, RunState
from tests.contracts.support import CONTRACTS, load_json

ROOT = Path(__file__).resolve().parents[1]

#: The global run state vocabulary and its terminal subset are *derived* from the Domain. The
#: schema is the second statement of a fact the code owns, so the expectation must be too.
RUN_STATES: list[str] = [state.value for state in RunState]
RUN_TERMINAL: list[str] = [name for name in RUN_STATES if RunState(name) in TERMINAL_STATES]

#: A stage execution's own status vocabulary has no Domain source of truth, and deliberately
#: so: the Domain knows nothing about stages. The literal here therefore *is* the pin. There is
#: no ``PENDING`` and no ``QUEUED`` — a record exists only once the stage has begun.
STAGE_STATUSES: list[str] = ["RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"]

#: A stage has finished exactly when its status is not ``RUNNING``, so the conditional that
#: requires ``finished_at`` is derived from the status vocabulary rather than restated.
STAGE_TERMINAL: list[str] = [name for name in STAGE_STATUSES if name != "RUNNING"]

#: The two accepted operating modes. The vocabulary is closed, mandatory and case-sensitive:
#: a run whose authorised mode was never stated is not a valid request, and an invented
#: third mode is rejected by the contract before any component could act on it.
SCAN_MODES: list[str] = ["PUBLIC_NON_INVASIVE", "OWNER_VERIFIED_CONTROLLED"]

#: Every closed vocabulary this module pins, as ``(schema file, JSON pointer) -> exact value``.
PINNED: dict[tuple[str, str], Any] = {
    ("analysis-run-request.v1.json", "#/properties/scan_mode/enum"): SCAN_MODES,
    ("analysis-run-state.v1.json", "#/properties/state/enum"): RUN_STATES,
    ("analysis-run-state.v1.json", "#/allOf/0/if/properties/state/enum"): RUN_TERMINAL,
    ("analysis-run-state.v1.json", "#/allOf/1/if/properties/state/const"): "FAILED",
    ("stage-execution-record.v1.json", "#/properties/status/enum"): STAGE_STATUSES,
    ("stage-execution-record.v1.json", "#/allOf/0/if/properties/status/enum"): STAGE_TERMINAL,
}

#: The one vocabulary a generic registry rule already owns: every contract's ``schema_version``
#: is pinned against that contract's registered version, for every contract, by the test named
#: here. Naming the owner keeps the coverage test below complete without stating the fact
#: twice, and the owner is checked to exist so a delegation cannot go stale.
VERSION_POINTER = "#/properties/schema_version/const"
VERSION_OWNER = (
    "tests/contracts/test_schema_meta.py",
    "test_every_contract_is_a_closed_object_pinning_its_own_version",
)
PINNED_ELSEWHERE: dict[tuple[str, str], tuple[str, str]] = {
    (Path(entry["schema"]).name, VERSION_POINTER): VERSION_OWNER for entry in CONTRACTS.entries()
}


def iter_vocabularies(node: Any, path: str = "#") -> Iterator[tuple[str, Any]]:
    """Every ``enum`` and ``const`` in a schema, as ``(JSON pointer, declared value)``."""
    if isinstance(node, dict):
        for keyword in ("enum", "const"):
            if keyword in node:
                yield f"{path}/{keyword}", node[keyword]
        for key, value in node.items():
            yield from iter_vocabularies(value, f"{path}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from iter_vocabularies(value, f"{path}/{index}")


def declared_vocabularies() -> dict[tuple[str, str], Any]:
    """Every closed vocabulary in every schema the manifest names. The inventory is the data."""
    return {
        (path.name, pointer): value
        for path in CONTRACTS.all_schema_paths()
        for pointer, value in iter_vocabularies(load_json(path))
    }


DECLARED = declared_vocabularies()
PINNED_IDS = [f"{name}{pointer}" for name, pointer in PINNED]


def _pin_id(item: tuple[tuple[str, str], Any]) -> str:
    (name, pointer), _ = item
    return f"{name}{pointer}"


# --- the pins ---------------------------------------------------------------------------------


@pytest.mark.parametrize("item", sorted(PINNED.items()), ids=_pin_id)
def test_a_pinned_vocabulary_is_exactly_what_this_module_declares(
    item: tuple[tuple[str, str], Any],
) -> None:
    """Not a subset and not a superset: widening or narrowing the set fails here."""
    (name, pointer), expected = item
    assert DECLARED[(name, pointer)] == expected, (
        f"{name}{pointer}: the registry declares {DECLARED[(name, pointer)]!r}, "
        f"this module pins {expected!r}"
    )


def test_every_closed_vocabulary_in_the_registry_is_pinned_or_delegated() -> None:
    """A closed vocabulary nobody pinned is the hole this module exists to close."""
    covered = set(PINNED) | set(PINNED_ELSEWHERE)
    unpinned = sorted(set(DECLARED) - covered)
    stale = sorted(covered - set(DECLARED))
    assert unpinned == [], f"closed vocabularies nobody pins: {unpinned}"
    assert stale == [], f"pinned vocabularies the registry no longer declares: {stale}"


@pytest.mark.parametrize("owner", sorted(set(PINNED_ELSEWHERE.values())), ids=lambda o: o[1])
def test_a_delegated_vocabulary_names_a_test_that_exists(owner: tuple[str, str]) -> None:
    """A delegation to a test that was renamed or deleted would exempt a vocabulary silently."""
    relative, function = owner
    source = (ROOT / relative).read_text(encoding="utf-8")
    assert f"def {function}(" in source, f"{relative} declares no {function}"


# --- the canaries -----------------------------------------------------------------------------


def test_the_registry_declares_something_to_pin() -> None:
    """An empty inventory would make every assertion above vacuously true."""
    assert len(DECLARED) >= len(PINNED) + len(PINNED_ELSEWHERE) > 0


def test_the_vocabulary_scanner_finds_a_planted_vocabulary() -> None:
    """The scanner is proven to see an ``enum`` and a ``const``, nested and inside a list."""
    planted = {
        "properties": {"mode": {"const": "PLANTED"}},
        "allOf": [{"if": {"properties": {"mode": {"enum": ["PLANTED", "OTHER"]}}}}],
    }
    found = dict(iter_vocabularies(planted))
    assert found["#/properties/mode/const"] == "PLANTED"
    assert found["#/allOf/0/if/properties/mode/enum"] == ["PLANTED", "OTHER"]


def test_the_coverage_rule_reports_a_vocabulary_the_pins_do_not_cover() -> None:
    """Canary for the coverage test: an unpinned vocabulary is reported, never absorbed.

    Deliberately synthetic. Planting into the real inventory would make this canary fail
    alongside the rule it guards, which proves nothing about the rule.
    """
    planted = ("planted.v1.json", "#/properties/x/enum")
    covered = set(PINNED) | set(PINNED_ELSEWHERE)
    assert sorted({planted} - covered) == [planted]
