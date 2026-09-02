"""AC3 / AC5: targeted invalid documents fail, deterministically, for the stated reason.

Each case under ``fixtures/invalid/<contract>/`` is one document plus an ``.expect.json``
sidecar naming the ``(pointer, keyword)`` violations that prove the point. The expected set
must be a subset of what the validator reports (a conditional rule often reports one more
generic violation alongside the specific one); running twice must report identical tuples.
"""

from pathlib import Path

import pytest

from tests.contracts.support import (
    FIXTURES_DIR,
    contract_entries,
    invalid_fixture_cases,
    load_json,
    validate,
)

CASES = invalid_fixture_cases()
IDS = [f"{contract}/{case}" for contract, case, _, _ in CASES]


@pytest.mark.parametrize(("contract", "case", "document_path", "expect_path"), CASES, ids=IDS)
def test_invalid_document_fails_for_the_expected_reason(
    contract: str, case: str, document_path: Path, expect_path: Path
) -> None:
    assert expect_path.is_file(), f"{contract}/{case}: missing .expect.json sidecar"
    expectation = load_json(expect_path)
    assert expectation["proves"].strip(), f"{contract}/{case}: say what the case proves"
    expected = {(v["pointer"], v["keyword"]) for v in expectation["violations"]}
    assert expected, f"{contract}/{case}: name at least one expected violation"

    document = load_json(document_path)
    first = validate(contract, document)
    second = validate(contract, document)

    assert first, f"{contract}/{case}: the document validated but was expected to fail"
    assert first == second, f"{contract}/{case}: validation is not deterministic"
    actual = {(v.pointer, v.keyword) for v in first}
    assert expected <= actual, (
        f"{contract}/{case}: expected {sorted(expected)} within {sorted(actual)}\n"
        + "\n".join(f"  {v.pointer} [{v.keyword}] {v.message}" for v in first)
    )


def test_every_contract_has_at_least_one_invalid_case() -> None:
    covered = {contract for contract, _, _, _ in CASES}
    missing = [entry["name"] for entry in contract_entries() if entry["name"] not in covered]
    assert missing == [], f"contracts without an invalid fixture: {missing}"


def test_fixture_directories_name_real_contracts() -> None:
    known = {entry["name"] for entry in contract_entries()}
    unknown = sorted({contract for contract, _, _, _ in CASES} - known)
    assert unknown == [], f"fixture directories for unknown contracts: {unknown}"


def test_every_fixture_document_has_a_sidecar_and_vice_versa() -> None:
    for _contract, _case, document_path, expect_path in CASES:
        assert expect_path.is_file(), f"orphan fixture document: {document_path}"
    documents = {document_path for _, _, document_path, _ in CASES}
    for sidecar in FIXTURES_DIR.glob("*/*.expect.json"):
        document = sidecar.with_name(sidecar.name.removesuffix(".expect.json") + ".json")
        assert document in documents, f"orphan sidecar without a document: {sidecar}"


def test_invalid_case_count_canary() -> None:
    """Discovery must have found the targeted inventory, not an empty directory."""
    assert len(CASES) >= 45
