"""Targeted invalid documents fail, deterministically, for the stated structural reason.

Each contract directory under ``fixtures/invalid/`` holds its case documents plus one
``expectations.json`` index mapping every case to the ``(pointer, keyword)`` violations that
prove the point — one index per contract, never one sidecar per case. Expectations are
structural only: a validator's free text is never persisted, so an upgrade of the validator
cannot turn a wording change into a red test.

The expected set must be a subset of what the validator reports, because a conditional rule
often reports one broader violation alongside the specific one.
"""

from __future__ import annotations

import pytest

from tests.contracts.support import (
    CONTRACTS,
    EXPECTATIONS_FILENAME,
    FIXTURES_DIR,
    InvalidCase,
    invalid_fixture_cases,
    load_json,
)

CASES = invalid_fixture_cases()
IDS = [case.id for case in CASES]


def test_the_fixture_set_is_not_empty() -> None:
    """Canary: without cases, every parametrised assertion below passes over an empty list."""
    assert CASES, f"no invalid fixture case discovered under {FIXTURES_DIR}"


def test_every_registered_contract_has_at_least_one_invalid_case() -> None:
    covered = {case.contract for case in CASES}
    missing = [entry["name"] for entry in CONTRACTS.entries() if entry["name"] not in covered]
    assert missing == [], f"contracts without an invalid fixture: {missing}"


def test_fixture_directories_name_registered_contracts() -> None:
    unknown = sorted({case.contract for case in CASES} - set(CONTRACTS.names()))
    assert unknown == [], f"fixture directories for unregistered contracts: {unknown}"


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_case_and_expectation_are_paired(case: InvalidCase) -> None:
    assert case.document_path is not None, (
        f"{case.id}: {case.index_path.name} names a case with no document"
    )
    assert case.expectation is not None, (
        f"{case.id}: document has no entry in {EXPECTATIONS_FILENAME}"
    )
    assert case.expectation["proves"].strip(), f"{case.id}: say what the case proves"
    assert case.expected_keys(), f"{case.id}: name at least one expected violation"


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_invalid_document_fails_for_the_expected_reason(case: InvalidCase) -> None:
    assert case.document_path is not None and case.expectation is not None, case.id
    document = load_json(case.document_path)
    first = CONTRACTS.validate(case.contract, document)
    second = CONTRACTS.validate(case.contract, document)

    assert first, f"{case.id}: the document validated but was expected to fail"
    assert first == second, f"{case.id}: validation is not deterministic"
    actual = {violation.key for violation in first}
    assert case.expected_keys() <= actual, (
        f"{case.id}: expected {sorted(case.expected_keys())} within {sorted(actual)}\n"
        + "\n".join(f"  {v.pointer} [{v.keyword}] {v.message}" for v in first)
    )


def test_expectations_record_no_validator_free_text() -> None:
    """Only ``pointer`` and ``keyword`` are stable; a persisted message is a brittle expectation."""
    for index_path in sorted(FIXTURES_DIR.glob(f"*/{EXPECTATIONS_FILENAME}")):
        index = load_json(index_path)
        for name, case in index["cases"].items():
            for violation in case["violations"]:
                unexpected = sorted(set(violation) - {"pointer", "keyword"})
                assert unexpected == [], (
                    f"{index_path.parent.name}/{name}: expectation carries {unexpected}; "
                    "expectations are structural (pointer/keyword) only"
                )


def test_every_contract_directory_carries_exactly_one_expectation_index() -> None:
    for contract_dir in sorted(p for p in FIXTURES_DIR.iterdir() if p.is_dir()):
        index_path = contract_dir / EXPECTATIONS_FILENAME
        assert index_path.is_file(), f"{contract_dir.name}: missing {EXPECTATIONS_FILENAME}"
        assert load_json(index_path)["contract"] == contract_dir.name
        sidecars = sorted(p.name for p in contract_dir.glob("*.expect.json"))
        assert sidecars == [], (
            f"{contract_dir.name}: per-case sidecars found ({sidecars}); "
            f"expectations belong in {EXPECTATIONS_FILENAME}"
        )
