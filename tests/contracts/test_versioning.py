"""Per-contract version identity and acceptance.

Each contract is versioned in its own right: the registry entry, the schema's ``$id`` and the
``const`` on ``schema_version`` are three statements of one fact and must agree. There is no
global contracts version acting as the semantic authority for every contract, so a later
slice can register ``foo`` at 1.0.0 next to ``bar`` at 2.1.0 without touching this file.
"""

from __future__ import annotations

import copy
import re
from typing import Any

import pytest

from tests.contracts.support import (
    CONTRACTS,
    ContractNotFound,
    load_json,
    to_problem,
    validate,
)

ENTRIES = CONTRACTS.entries()
NAMES = CONTRACTS.names()
SEMVER = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")

#: Versions no v1 contract may accept. None of them is the version of any registered contract;
#: `test_the_rejected_versions_are_actually_foreign` proves that rather than assuming it.
FOREIGN_VERSIONS = ["1.0", "1.0.1", "1.1.0", "2.0.0", "0.9.0", "v1.0.0", ""]


def _first_example(name: str) -> dict[str, Any]:
    return load_json(CONTRACTS.example_paths(name)[0])


def test_there_is_something_to_version() -> None:
    assert ENTRIES, "canary: no contract is registered, so no version rule is exercised"


@pytest.mark.parametrize("entry", ENTRIES, ids=NAMES)
def test_registry_id_schema_id_and_version_agree(entry: dict[str, Any]) -> None:
    name, version = entry["name"], entry["version"]
    assert SEMVER.fullmatch(version), f"{name}: version {version!r} is not a semantic version"
    expected_id = CONTRACTS.expected_schema_id(name, version)
    assert entry["id"] == expected_id, f"{name}: registry id disagrees with name/version"
    schema = load_json(CONTRACTS.path / entry["schema"])
    assert schema["$id"] == expected_id, f"{name}: schema $id disagrees with the registry"


def test_the_rejected_versions_are_actually_foreign() -> None:
    """Canary: the rejection cases below only mean something if no contract is at those versions."""
    registered = {entry["version"] for entry in ENTRIES}
    assert not registered & set(FOREIGN_VERSIONS)


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("version", FOREIGN_VERSIONS, ids=repr)
def test_an_unsupported_schema_version_is_rejected_by_const(name: str, version: str) -> None:
    document = _first_example(name)
    document["schema_version"] = version
    found = validate(name, document)
    assert ("/schema_version", "const") in {v.key for v in found}


@pytest.mark.parametrize("name", NAMES)
def test_a_missing_schema_version_is_rejected_at_the_root(name: str) -> None:
    document = _first_example(name)
    del document["schema_version"]
    found = validate(name, document)
    assert ("", "required") in {v.key for v in found}


@pytest.mark.parametrize("name", NAMES)
def test_an_unsupported_version_maps_to_schema_version_unsupported(name: str) -> None:
    document = _first_example(name)
    document["schema_version"] = "9.9.9"
    problem = to_problem(name, validate(name, document))
    assert problem["code"] == "SCHEMA_VERSION_UNSUPPORTED"
    assert validate("problem", problem) == ()


@pytest.mark.parametrize("name", NAMES)
def test_an_unrecognised_root_property_is_rejected(name: str) -> None:
    document = _first_example(name)
    document["unexpected_future_property"] = {"anything": True}
    found = validate(name, document)
    assert ("", "additionalProperties") in {v.key for v in found}


@pytest.mark.parametrize("name", NAMES)
def test_an_optional_property_may_not_be_null(name: str) -> None:
    """Category rule at the root: optional means optional non-null, never nullable."""
    schema = load_json(CONTRACTS.path / CONTRACTS.entry(name)["schema"])
    optional = [p for p in schema["properties"] if p not in schema["required"]]
    document = _first_example(name)
    for member in optional:
        candidate = copy.deepcopy(document)
        candidate[member] = None
        assert validate(name, candidate), f"{name}.{member}: null accepted for an optional property"


def test_an_unregistered_contract_name_raises_contract_not_found() -> None:
    unregistered = "no-such-contract"
    assert unregistered not in NAMES
    with pytest.raises(ContractNotFound) as info:
        CONTRACTS.validator_for(unregistered)
    assert info.value.code == "CONTRACT_NOT_FOUND"
    assert info.value.code in {item["code"] for item in CONTRACTS.problem_codes()}


def test_non_json_constants_are_rejected_at_load_time(tmp_path: Any) -> None:
    """A NaN value would slip past minimum/maximum (both compare False); the loader refuses it."""
    for literal in ("NaN", "Infinity", "-Infinity"):
        path = tmp_path / f"{literal.strip('-')}.json"
        path.write_text('{"schema_version": "1.0.0", "value": ' + literal + "}", encoding="utf-8")
        with pytest.raises(ValueError, match="non-JSON constant"):
            load_json(path)
