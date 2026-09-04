"""Every example the registry lists validates against the contract that lists it."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.contracts.support import CONTRACTS, load_json, validate

CASES = [
    (entry["name"], entry["version"], CONTRACTS.path / example)
    for entry in CONTRACTS.entries()
    for example in entry["examples"]
]
IDS = [path.name for _, _, path in CASES]


def test_every_registered_contract_contributes_at_least_one_example() -> None:
    """Canary and rule in one: parametrisation below must not have covered zero contracts."""
    covered = {name for name, _, _ in CASES}
    missing = [entry["name"] for entry in CONTRACTS.entries() if entry["name"] not in covered]
    assert missing == [], f"contracts without a valid example: {missing}"
    assert covered, "no contract is registered, so no example was checked"


@pytest.mark.parametrize(("name", "version", "path"), CASES, ids=IDS)
def test_example_validates_with_zero_violations(name: str, version: str, path: Path) -> None:
    document = load_json(path)
    assert document["schema_version"] == version, (
        f"{path.name}: declares {document['schema_version']!r}, "
        f"but {name} is registered at {version!r}"
    )
    found = validate(name, document)
    assert found == (), "\n".join(f"{v.pointer} [{v.keyword}] {v.message}" for v in found)


@pytest.mark.parametrize(("name", "version", "path"), CASES, ids=IDS)
def test_example_validation_is_deterministic(name: str, version: str, path: Path) -> None:
    document = load_json(path)
    assert validate(name, document) == validate(name, document)
