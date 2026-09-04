"""Per-contract version identity and acceptance.

Each contract is versioned in its own right: the registry entry, the schema's ``$id`` and the
``const`` on ``schema_version`` are three statements of one fact and must agree. There is no
global contracts version, and no legitimate version is forbidden project-wide: a version is
foreign *relative to one contract*, derived here from that contract's own version.
``test_registry_evolution`` registers a second contract at another version to prove it.
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

#: Not semantic versions at all: a shape rule, never a blacklist of legitimate values.
MALFORMED = ["1.0", "v1.0.0", "1.0.0.0", "latest", ""]


def _foreign_to(version: str) -> list[str]:
    """The next patch, minor and major of ``version``: legitimate versions, foreign to it."""
    major, minor, patch = (int(part) for part in version.split("."))
    return [f"{major}.{minor}.{patch + 1}", f"{major}.{minor + 1}.0", f"{major + 1}.0.0"]


#: ``(contract, version)`` pairs, derived from the registry and each contract's own version.
FOREIGN = [(e["name"], v) for e in ENTRIES for v in _foreign_to(e["version"])]
REJECTED = FOREIGN + [(name, bad) for name in NAMES for bad in MALFORMED]


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


def test_each_rejection_case_is_foreign_or_malformed() -> None:
    """Canary: a case proves nothing unless it differs from the contract's own version."""
    assert FOREIGN, "canary: no foreign version was derived, so no rejection is exercised"
    assert all(SEMVER.fullmatch(v) and v != CONTRACTS.entry(n)["version"] for n, v in FOREIGN)
    assert not any(SEMVER.fullmatch(bad) for bad in MALFORMED)


@pytest.mark.parametrize(("name", "version"), REJECTED, ids=[f"{n}@{v!r}" for n, v in REJECTED])
def test_an_unsupported_schema_version_is_rejected_by_const(name: str, version: str) -> None:
    document = dict(_first_example(name), schema_version=version)
    assert ("/schema_version", "const") in {v.key for v in validate(name, document)}


@pytest.mark.parametrize("name", NAMES)
def test_a_missing_schema_version_is_rejected_at_the_root(name: str) -> None:
    document = _first_example(name)
    del document["schema_version"]
    assert ("", "required") in {v.key for v in validate(name, document)}


@pytest.mark.parametrize("name", NAMES)
def test_an_unsupported_version_and_a_missing_one_carry_different_codes(name: str) -> None:
    """Regression: a version this contract does not support is not the same fact as none."""
    foreign = _foreign_to(CONTRACTS.entry(name)["version"])[0]
    missing = _first_example(name)
    del missing["schema_version"]
    unsupported = to_problem(name, validate(name, dict(missing, schema_version=foreign)))
    absent = to_problem(name, validate(name, missing))
    assert unsupported["code"] == "SCHEMA_VERSION_UNSUPPORTED"
    assert absent["code"] == "CONTRACT_VALIDATION_FAILED"
    assert validate("problem", unsupported) == () and validate("problem", absent) == ()


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
