"""Version acceptance, closed roots, the shared lexical rules, and the problem contract.

Every case here is generic over the manifest, so a contract added later is covered without a
new test, and every rejection is proven by the assertion keyword that produced it.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from tests.contracts.support import (
    CONTRACTS_DIR,
    CONTRACTS_VERSION,
    REQUIRED_PROBLEM_CODES,
    ContractNotFound,
    contract_entries,
    load_json,
    manifest,
    to_problem,
    validate,
    validator_for,
    validator_for_definition,
    violations_of,
)

NAMES = [entry["name"] for entry in contract_entries()]


def _first_example(name: str) -> dict[str, Any]:
    entry = next(e for e in contract_entries() if e["name"] == name)
    return load_json(CONTRACTS_DIR / entry["examples"][0])


# --- D: only the accepted schema_version validates ------------------------------------------


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("version", ["1.0", "1.0.1", "1.1.0", "2.0.0", "0.9.0", "v1.0.0", ""])
def test_any_other_schema_version_is_rejected_by_const(name: str, version: str) -> None:
    document = _first_example(name)
    document["schema_version"] = version
    found = validate(name, document)
    assert ("/schema_version", "const") in {(v.pointer, v.keyword) for v in found}


@pytest.mark.parametrize("name", NAMES)
def test_missing_schema_version_is_rejected_at_the_root(name: str) -> None:
    document = _first_example(name)
    del document["schema_version"]
    found = validate(name, document)
    assert ("", "required") in {(v.pointer, v.keyword) for v in found}


@pytest.mark.parametrize("name", NAMES)
def test_wrong_version_maps_to_schema_version_unsupported(name: str) -> None:
    document = _first_example(name)
    document["schema_version"] = "2.0.0"
    problem = to_problem(name, validate(name, document))
    assert problem["code"] == "SCHEMA_VERSION_UNSUPPORTED"
    assert validate("problem", problem) == ()


def test_unknown_contract_name_raises_contract_not_found() -> None:
    with pytest.raises(ContractNotFound) as info:
        validator_for("measurement-record-v2")
    assert info.value.code == "CONTRACT_NOT_FOUND"
    assert info.value.code in REQUIRED_PROBLEM_CODES


# --- E: closed roots ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", NAMES)
def test_an_unrecognised_root_property_is_rejected(name: str) -> None:
    document = _first_example(name)
    document["unexpected_future_property"] = {"anything": True}
    found = validate(name, document)
    assert ("", "additionalProperties") in {(v.pointer, v.keyword) for v in found}


@pytest.mark.parametrize("name", NAMES)
def test_an_optional_property_may_not_be_null(name: str) -> None:
    """Category rule at the root: optional means optional non-null, never nullable."""
    entry = next(e for e in contract_entries() if e["name"] == name)
    schema = load_json(CONTRACTS_DIR / entry["schema"])
    optional = [p for p in schema["properties"] if p not in schema["required"]]
    document = _first_example(name)
    for member in optional:
        candidate = copy.deepcopy(document)
        candidate[member] = None
        found = validate(name, candidate)
        assert found, f"{name}.{member}: null was accepted for an optional property"


# --- F: timestamps -----------------------------------------------------------------------------

GOOD_TIMESTAMPS = [
    "2026-09-02T10:15:30Z",
    "2026-09-02T10:15:30.2Z",
    "2026-09-02T10:15:30.250Z",
    "2026-09-02T10:15:30.123456789Z",
    "2026-12-31T23:59:60Z",
]

BAD_TIMESTAMPS = [
    "2026-09-02T10:15:30+02:00",
    "2026-09-02T10:15:30+00:00",
    "2026-09-02T10:15:30-00:00",
    "2026-09-02T10:15:30",
    "2026-09-02T10:15:30z",
    "2026-09-02t10:15:30Z",
    "2026-09-02 10:15:30Z",
    "2026-09-02",
    "2026-09-02T10:15Z",
    "2026-13-02T10:15:30Z",
    "2026-09-32T10:15:30Z",
    "2026-09-02T24:00:00Z",
    "2026-09-02T10:60:00Z",
    "2026-09-02T10:15:30.1234567890Z",
    "2026-09-02T10:15:30Z\n",
    " 2026-09-02T10:15:30Z",
    "1725272130",
    "",
]


@pytest.mark.parametrize("value", GOOD_TIMESTAMPS)
def test_utc_z_timestamps_are_accepted(value: str) -> None:
    assert violations_of(validator_for_definition("timestamp"), value) == ()


@pytest.mark.parametrize("value", BAD_TIMESTAMPS, ids=repr)
def test_non_utc_or_malformed_timestamps_are_rejected(value: str) -> None:
    found = violations_of(validator_for_definition("timestamp"), value)
    assert [v.keyword for v in found] == ["pattern"]


def test_timestamp_as_a_number_is_rejected_by_type() -> None:
    found = violations_of(validator_for_definition("timestamp"), 1725272130)
    assert "type" in {v.keyword for v in found}


# --- G: stable identifiers without an id technology ------------------------------------------

GOOD_IDS = [
    "run_01J6ZK3M8Q0X4V9R2T7B5N1C6D",
    "3f9c1c8e-4a4b-4d5e-9d6f-1a2b3c4d5e6f",
    "MEAS-000042",
    "42",
    "sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
    "a",
    "with inner space",
    "ünïcödé-id",
    "x" * 128,
]

BAD_IDS = [
    ("", ["minLength", "pattern"]),
    (" ", ["pattern"]),
    (" leading", ["pattern"]),
    ("trailing ", ["pattern"]),
    ("trailing-tab\t", ["pattern"]),
    ("line\nbreak", ["pattern"]),
    ("trailing-newline\n", ["pattern"]),
    ("x" * 129, ["maxLength"]),
]


@pytest.mark.parametrize("value", GOOD_IDS)
def test_opaque_ids_of_any_technology_are_accepted(value: str) -> None:
    assert violations_of(validator_for_definition("id"), value) == ()


@pytest.mark.parametrize(("value", "keywords"), BAD_IDS, ids=[repr(v) for v, _ in BAD_IDS])
def test_empty_padded_or_multiline_ids_are_rejected(value: str, keywords: list[str]) -> None:
    found = violations_of(validator_for_definition("id"), value)
    assert sorted(v.keyword for v in found) == sorted(keywords)


def test_id_as_a_number_is_rejected_by_type() -> None:
    found = violations_of(validator_for_definition("id"), 42)
    assert "type" in {v.keyword for v in found}


# --- tokens, codes and URLs ---------------------------------------------------------------------


@pytest.mark.parametrize("value", ["internal", "self_service", "pxapi.http_probe", "V2-beta"])
def test_tokens_are_accepted(value: str) -> None:
    assert violations_of(validator_for_definition("token"), value) == ()


@pytest.mark.parametrize("value", ["", "1abc", "has space", "_x", "x\n", "x" * 65], ids=repr)
def test_malformed_tokens_are_rejected(value: str) -> None:
    assert violations_of(validator_for_definition("token"), value)


@pytest.mark.parametrize("definition", ["text", "short_text"])
@pytest.mark.parametrize("value", ["", " ", "   ", "\t", " \t "], ids=repr)
def test_whitespace_only_text_is_rejected(definition: str, value: str) -> None:
    assert violations_of(validator_for_definition(definition), value)


def test_text_allows_line_breaks_but_short_text_does_not() -> None:
    assert violations_of(validator_for_definition("text"), "first line\nsecond line") == ()
    assert violations_of(validator_for_definition("short_text"), "first line\nsecond line")
    assert violations_of(validator_for_definition("short_text"), " padded label ") == ()


@pytest.mark.parametrize("value", ["PROVIDER_FAILURE", "OK", "A1", "SOME_FUTURE_CODE_2"])
def test_codes_are_accepted(value: str) -> None:
    assert violations_of(validator_for_definition("code"), value) == ()


@pytest.mark.parametrize(
    "value", ["", "A", "lower", "Mixed_Case", "HAS SPACE", "1A", "A\n"], ids=repr
)
def test_malformed_codes_are_rejected(value: str) -> None:
    assert violations_of(validator_for_definition("code"), value)


@pytest.mark.parametrize(
    "value", ["https://www.example-handwerk.de/", "http://example.org/path?q=1#frag"]
)
def test_http_urls_are_accepted(value: str) -> None:
    assert violations_of(validator_for_definition("url"), value) == ()


@pytest.mark.parametrize(
    "value",
    ["ftp://example.org/", "file:///etc/passwd", "www.example.org", "https://", "https://a b", ""],
    ids=repr,
)
def test_non_http_urls_are_rejected(value: str) -> None:
    assert violations_of(validator_for_definition("url"), value)


# --- S / T: problem semantics ------------------------------------------------------------------

_INTERNAL_FRAGMENTS = (
    "Traceback (most recent call last)",
    "/Users/",
    "/srv/",
    "\n",
    "password=",
    "KeyError",
)


def test_problem_built_from_hostile_validator_output_is_sanitised() -> None:
    """A validator message carrying a traceback, a path and a secret never reaches the document."""
    from tests.contracts.support import Violation

    hostile = (
        "Traceback (most recent call last):\n"
        '  File "/Users/someone/pxapi/app.py", line 12, in validate\n'
        "KeyError: 'password=hunter2'"
    )
    found = (
        Violation("/measured_at", "pattern", hostile),
        Violation("", "required", hostile),
    )
    problem = to_problem("measurement-record", found)
    assert validate("problem", problem) == ()
    assert problem["code"] == "CONTRACT_VALIDATION_FAILED"
    rendered = repr(problem)
    for fragment in _INTERNAL_FRAGMENTS:
        assert fragment not in rendered, fragment
    assert [e["pointer"] for e in problem["errors"]] == ["/measured_at", ""]
    assert [e["keyword"] for e in problem["errors"]] == ["pattern", "required"]


def test_problem_rendering_is_deterministic_and_order_independent() -> None:
    from tests.contracts.support import Violation

    first = to_problem("x", (Violation("/a", "type", "one"), Violation("", "required", "two")))
    second = to_problem(
        "x", (Violation("/a", "type", "changed text"), Violation("", "required", ""))
    )
    assert first == second  # the free text never influences the document


def test_registered_problem_codes_validate_against_the_problem_contract() -> None:
    for item in manifest()["problem_codes"]:
        document = {
            "schema_version": CONTRACTS_VERSION,
            "code": item["code"],
            "title": "Registered problem",
            "detail": "A registered code produces a valid document.",
            "errors": [],
        }
        assert validate("problem", document) == (), item["code"]


def test_an_unknown_future_problem_code_remains_consumable() -> None:
    """T: the code is an open token, so a code registered later validates today."""
    document = {
        "schema_version": CONTRACTS_VERSION,
        "code": "RATE_LIMIT_EXCEEDED",
        "title": "Rate limit exceeded",
        "detail": "The requester exceeded its quota; retry later.",
        "errors": [],
    }
    assert "RATE_LIMIT_EXCEEDED" not in {c["code"] for c in manifest()["problem_codes"]}
    assert validate("problem", document) == ()


def test_non_json_constants_are_rejected_at_load_time(tmp_path: Path) -> None:
    """A NaN score would slip past minimum/maximum (both compare False); the loader refuses it."""
    for literal in ("NaN", "Infinity", "-Infinity"):
        path = tmp_path / f"{literal.strip('-')}.json"
        path.write_text('{"schema_version": "1.0.0", "value": ' + literal + "}", encoding="utf-8")
        with pytest.raises(ValueError, match="non-JSON constant"):
            load_json(path)


def test_problem_carries_no_transport_binding() -> None:
    schema = load_json(CONTRACTS_DIR / "schemas" / "problem.v1.json")
    assert not {"status", "type", "instance", "http_status"} & set(schema["properties"])
