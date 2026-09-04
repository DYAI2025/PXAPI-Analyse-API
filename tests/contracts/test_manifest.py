"""The registry is structurally valid, and it is the only source of the contract inventory.

Every assertion here is generic over the registry data. There is deliberately no test that
the registry holds a particular contract, a particular set of names or a particular count:
registering a contract is an additive change that must not require editing this file.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from tests.contracts.support import (
    CONTRACTS,
    REQUIRED_ENTRY_MEMBERS,
    REQUIRED_SHARED_MEMBERS,
    contract_entries,
    load_json,
    manifest,
)

CONTRACT_NAME = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
ENTRIES = contract_entries()
IDS = [entry["name"] for entry in ENTRIES]


def test_the_registry_is_not_empty() -> None:
    """A canary against a vacuous suite: every parametrised test below would silently pass."""
    assert ENTRIES, "the registry declares no contract, so nothing below is actually checked"


def test_registry_metadata_is_complete() -> None:
    meta = manifest()["registry"]
    assert meta["dialect"] == "https://json-schema.org/draft/2020-12/schema"
    assert meta["id_namespace"].endswith(":")
    assert meta["roles"], "the registry must declare its role vocabulary"
    assert meta["statuses"], "the registry must declare its status vocabulary"
    assert CONTRACT_NAME.fullmatch(meta["version"].replace(".", "-")), meta["version"]


@pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
def test_entry_declares_every_required_member(entry: dict[str, Any]) -> None:
    missing = [member for member in REQUIRED_ENTRY_MEMBERS if member not in entry]
    assert missing == [], f"{entry.get('name')}: registry entry lacks {missing}"
    unexpected = sorted(set(entry) - set(REQUIRED_ENTRY_MEMBERS))
    assert unexpected == [], f"{entry['name']}: unrecognised registry member(s) {unexpected}"


@pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
def test_entry_uses_the_declared_vocabularies(entry: dict[str, Any]) -> None:
    assert CONTRACT_NAME.fullmatch(entry["name"]), entry["name"]
    assert entry["role"] in CONTRACTS.roles(), entry["name"]
    assert entry["status"] in CONTRACTS.statuses(), entry["name"]
    assert entry["owner_slice"].strip(), f"{entry['name']}: every contract names an owning slice"


def test_contract_names_and_ids_are_unique() -> None:
    names = [entry["name"] for entry in ENTRIES]
    ids = [entry["id"] for entry in ENTRIES]
    assert len(names) == len(set(names)), "duplicate contract name in the registry"
    assert len(ids) == len(set(ids)), "duplicate contract id in the registry"


def test_shared_definitions_are_structurally_valid_and_are_not_contracts() -> None:
    shared = CONTRACTS.shared_definitions()
    assert shared, "the registry must declare at least one shared definition file"
    for entry in shared:
        missing = [member for member in REQUIRED_SHARED_MEMBERS if member not in entry]
        assert missing == [], f"{entry.get('name')}: shared definition lacks {missing}"
    assert not {s["name"] for s in shared} & set(CONTRACTS.names()), (
        "a shared definition file is not a contract and must not be registered as one"
    )


@pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
def test_entry_points_at_existing_files(entry: dict[str, Any]) -> None:
    name = entry["name"]
    schema_path = CONTRACTS.path / entry["schema"]
    assert schema_path.is_file(), f"{name}: schema file missing: {entry['schema']}"
    assert entry["examples"], f"{name}: at least one valid example is required"
    for example in entry["examples"]:
        example_path = CONTRACTS.path / example
        assert example_path.is_file(), f"{name}: example file missing: {example}"
        assert example_path.name.startswith(f"{name}."), f"{name}: example named for another"
        assert example_path.name.endswith(".example.json")


def test_every_schema_file_on_disk_is_registered() -> None:
    listed = set(CONTRACTS.all_schema_paths())
    on_disk = set((CONTRACTS.path / "schemas").glob("*.json"))
    assert on_disk == listed, "schema files on disk and in the registry differ"


def test_every_example_file_on_disk_is_registered() -> None:
    listed = {CONTRACTS.path / example for entry in ENTRIES for example in entry["examples"]}
    on_disk = set((CONTRACTS.path / "examples").glob("*.json"))
    assert on_disk == listed, "example files on disk and in the registry differ"


def test_example_names_are_unique_across_contracts() -> None:
    examples = [Path(example).name for entry in ENTRIES for example in entry["examples"]]
    assert len(examples) == len(set(examples))


def test_registered_problem_codes_are_unique_and_explained() -> None:
    codes = [item["code"] for item in CONTRACTS.problem_codes()]
    assert codes, "the registry must register at least one problem code"
    assert len(codes) == len(set(codes)), "duplicate problem code"
    for item in CONTRACTS.problem_codes():
        assert item["meaning"].strip(), f"{item['code']} has no meaning"


def test_the_registry_carries_a_problem_code_policy() -> None:
    assert manifest()["problem_code_policy"].strip()


def test_no_registered_schema_file_is_empty() -> None:
    for path in CONTRACTS.all_schema_paths():
        assert isinstance(load_json(path), dict), f"{path.name}: not a JSON object"
