"""AC1: the manifest inventories exactly the eleven canonical contracts (plus the support set)."""

from pathlib import Path

import pytest

from tests.contracts.support import (
    CANONICAL_CONTRACT_NAMES,
    CONTRACTS_DIR,
    CONTRACTS_VERSION,
    DIALECT,
    REQUIRED_PROBLEM_CODES,
    SUPPORT_CONTRACT_NAMES,
    contract_entries,
    load_json,
    manifest,
    schema_id,
)


def test_manifest_lists_exactly_the_eleven_canonical_contracts_in_confluence_order() -> None:
    names = [entry["name"] for entry in manifest()["canonical"]]
    assert names == list(CANONICAL_CONTRACT_NAMES)
    assert len(names) == 11


def test_manifest_lists_exactly_the_four_support_contracts() -> None:
    names = [entry["name"] for entry in manifest()["support"]]
    assert names == list(SUPPORT_CONTRACT_NAMES)


def test_every_support_contract_carries_a_justification() -> None:
    for entry in manifest()["support"]:
        assert entry["justification"].strip(), f"{entry['name']} lacks a justification"


def test_common_is_a_shared_definition_and_not_a_contract() -> None:
    data = manifest()
    assert [shared["name"] for shared in data["shared_definitions"]] == ["common"]
    assert "common" not in {entry["name"] for entry in contract_entries()}


def test_manifest_version_and_dialect() -> None:
    data = manifest()
    assert data["contracts_version"] == CONTRACTS_VERSION
    assert data["dialect"] == DIALECT


def test_manifest_registers_the_required_problem_codes() -> None:
    codes = [item["code"] for item in manifest()["problem_codes"]]
    assert len(codes) == len(set(codes)), "duplicate problem code"
    assert set(REQUIRED_PROBLEM_CODES) <= set(codes)
    for item in manifest()["problem_codes"]:
        assert item["meaning"].strip(), f"{item['code']} has no meaning"


@pytest.mark.parametrize("entry", contract_entries(), ids=lambda e: e["name"])
def test_contract_entry_points_at_existing_files_with_matching_ids(entry: dict) -> None:
    name = entry["name"]
    schema_path = CONTRACTS_DIR / entry["schema"]
    assert schema_path.is_file(), f"{name}: schema file missing"
    assert schema_path.name == f"{name}.v1.json"
    schema = load_json(schema_path)
    assert schema["$schema"] == DIALECT
    assert schema["$id"] == schema_id(name)
    assert entry["examples"], f"{name}: at least one valid example is required"
    for example in entry["examples"]:
        example_path = CONTRACTS_DIR / example
        assert example_path.is_file(), f"{name}: example file missing: {example}"
        assert example_path.name.startswith(f"{name}."), f"{name}: example named for another"
        assert example_path.name.endswith(".example.json")


def test_every_schema_file_on_disk_is_listed_in_the_manifest() -> None:
    listed = {CONTRACTS_DIR / entry["schema"] for entry in contract_entries()}
    listed |= {CONTRACTS_DIR / shared["schema"] for shared in manifest()["shared_definitions"]}
    on_disk = set((CONTRACTS_DIR / "schemas").glob("*.json"))
    assert on_disk == listed, "schema files on disk and in the manifest differ"
    assert len(on_disk) == 16  # 11 canonical + 4 support + common


def test_every_example_file_on_disk_is_listed_in_the_manifest() -> None:
    listed = {
        CONTRACTS_DIR / example for entry in contract_entries() for example in entry["examples"]
    }
    on_disk = set((CONTRACTS_DIR / "examples").glob("*.json"))
    assert on_disk == listed, "example files on disk and in the manifest differ"


def test_example_names_are_unique_across_contracts() -> None:
    examples = [Path(ex).name for entry in contract_entries() for ex in entry["examples"]]
    assert len(examples) == len(set(examples))
