"""AC2: every contract has at least one valid example, and every listed example validates."""

from pathlib import Path

import pytest

from tests.contracts.support import (
    CONTRACTS_DIR,
    CONTRACTS_VERSION,
    contract_entries,
    example_paths,
    load_json,
    validate,
)

CASES = [
    (entry["name"], CONTRACTS_DIR / example)
    for entry in contract_entries()
    for example in entry["examples"]
]


@pytest.mark.parametrize(("name", "path"), CASES, ids=[p.name for _, p in CASES])
def test_example_validates_with_zero_violations(name: str, path: Path) -> None:
    document = load_json(path)
    assert document["schema_version"] == CONTRACTS_VERSION
    found = validate(name, document)
    assert found == (), "\n".join(f"{v.pointer} [{v.keyword}] {v.message}" for v in found)


def test_every_contract_has_at_least_one_example() -> None:
    for entry in contract_entries():
        assert example_paths(entry["name"]), entry["name"]


def test_example_count_canary() -> None:
    """The parametrisation above must have covered every contract, not silently zero."""
    assert len(CASES) >= 15
    assert {name for name, _ in CASES} == {entry["name"] for entry in contract_entries()}
