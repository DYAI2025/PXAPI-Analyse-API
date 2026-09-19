"""The page-acquisition vocabulary, the two derived values, and the producer invariants.

Three kinds of proof live here, and they are deliberately different kinds.

**Synchronisation.** ``AcquisitionOutcome`` is a Domain vocabulary, and the failure kinds it
has to be able to express live in a Port the Domain may not import. The token set is therefore
declared literally in the Domain and proved equal to ``RESPONSE_RECEIVED`` + every
``FetchFailureKind`` value in declaration order + ``RUNTIME_ERROR`` here, where importing both
is allowed. That equality is what lets a producer map a failure with
``AcquisitionOutcome(failure.kind.value)`` and never carry a translation table that can rot.

**Contract agreement.** ``is_contract_url`` decides whether an observed URL can be carried by
``measurement-record.source_url`` at all. The Domain may not import a validator, so the shape is
restated — and then pinned character for character against ``common.v1.json`` *and* checked
against the reference validator itself over a table of real values, including the classes where
``acquisition#/$defs/public_url`` and ``common#/$defs/url`` disagree (``C-PXAPI-020``).

**Producer invariants.** One isolated counterexample per declared rule, each asserting that
*exactly* that rule fires, plus a coverage test that fails when a rule has no counterexample.
The clean fixture is validated against the real registry first, so a red invariant test is
never explained by a fixture that was invalid to begin with.
"""

from __future__ import annotations

import hashlib
import http.client
import io
from collections.abc import Callable, Sequence
from typing import Any

import pytest

from pxapi.adapters.contracts.registry import ContractRegistry, load_json
from pxapi.config.contract_root import contract_root
from pxapi.domain.acquisition_digests import manifest_digests
from pxapi.domain.acquisition_semantics import ProducerInvariantViolated
from pxapi.domain.page_acquisition import (
    ACQUISITION_METHOD,
    ACQUISITION_METHOD_VERSION,
    COMMON_URL_PATTERN,
    HTTP_STATUS_MAX,
    HTTP_STATUS_MIN,
    MAX_CONTRACT_URL_LENGTH,
    MEASUREMENTS_WITHHELD_SOURCE_URL,
    OBSERVATION_MODE_STATIC_HTTP,
    PAGE_ACQUISITION_RECORD,
    PRODUCER_RULES,
    RECORDS_POINTER,
    AcquisitionOutcome,
    acquisition_violations,
    body_digest,
    is_contract_url,
    require_emittable_acquisition,
    withheld_reason_for,
)
from pxapi.ports.page_fetch import FetchFailureKind

CONTRACTS = ContractRegistry(contract_root())

RUN_ID = "run-0001"
MANIFEST_ID = "manifest-0001"
ORIGIN = "https://example.test/"
SECOND = "https://example.test/about"

#: A url_key that `acquisition#/$defs/public_url` admits and `common#/$defs/url` refuses: 2048
#: characters whose authority is 250 long, so the split authority/remainder budget accepts it
#: while the single 2040-character run after the scheme does not. C-PXAPI-020.
_H6_HOST = "a" * (250 - len(".example.test")) + ".example.test"
_H6_BASE = f"http://{_H6_HOST}/"
H6_URL = _H6_BASE + "b" * (MAX_CONTRACT_URL_LENGTH - len(_H6_BASE))


# --- fixtures -------------------------------------------------------------------------------


def sampling_manifest(url_keys: Sequence[str]) -> dict[str, Any]:
    """A contract-valid `sampling-manifest.v1` selecting exactly ``url_keys`` in rank order."""
    placeholder = "sha256:" + "0" * 64
    document: dict[str, Any] = {
        "schema_version": "1.0.0",
        "run_id": RUN_ID,
        "sampling_manifest_id": MANIFEST_ID,
        "generated_at": "2026-09-19T10:00:00Z",
        "inventory_ref": "inventory-0001",
        "inventory_output_digest": "sha256:" + "1" * 64,
        "policy_id": "CENSUS_FIRST_DETERMINISTIC",
        "policy_version": "1.0.0",
        "mode": "CENSUS",
        "selection_complete": True,
        "selections": [
            {
                "url_key": key,
                "selection_rank": rank,
                "selection_reason": "SEED" if rank == 1 else "CENSUS",
                "stratum": "UNCLASSIFIED",
            }
            for rank, key in enumerate(url_keys, start=1)
        ],
        "exclusions": [],
        "input_digest": placeholder,
        "output_digest": placeholder,
    }
    document["input_digest"], document["output_digest"] = manifest_digests(document)
    return document


def measurement(run_id: str, measurement_id: str, source_url: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "measurement_id": measurement_id,
        "metric_id": "HTTP_STATUS",
        "source_url": source_url,
        "observed_at": "2026-09-19T10:00:01Z",
        "collector": "STATIC_PAGE_BASELINE_COLLECTOR",
        "collector_version": "1.0.0",
        "assessment": {"collection_mode": "MEASURED", "result_state": "KNOWN"},
        "result": {"value_type": "INTEGER", "integer_value": 200},
    }


def evidence_for(measured: dict[str, Any], evidence_id: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "run_id": measured["run_id"],
        "evidence_id": evidence_id,
        "source_url": measured["source_url"],
        "observed_at": measured["observed_at"],
        "scenario": "SELECTED_PAGE_STATIC_FETCH",
        "collector": measured["collector"],
        "collector_version": measured["collector_version"],
        "assessment": dict(measured["assessment"]),
        "measurement_refs": [measured["measurement_id"]],
    }


def record(
    manifest: dict[str, Any],
    url_key: str,
    acquisition_id: str,
    measurement_refs: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "run_id": manifest["run_id"],
        "acquisition_id": acquisition_id,
        "sampling_manifest_ref": manifest["sampling_manifest_id"],
        "sampling_manifest_output_digest": manifest["output_digest"],
        "url_key": url_key,
        "observation_mode": OBSERVATION_MODE_STATIC_HTTP,
        "acquisition_method": ACQUISITION_METHOD,
        "acquisition_method_version": ACQUISITION_METHOD_VERSION,
        "acquired_at": "2026-09-19T10:00:01Z",
        "acquisition_outcome": AcquisitionOutcome.RESPONSE_RECEIVED.value,
        "http_status": 200,
        "final_url_key": url_key,
        "redirect_count": 0,
        "body_truncated": False,
        "body_decoded": True,
        "body_digest": body_digest(b"<html></html>"),
        "measurement_refs": measurement_refs,
    }


def clean_set() -> tuple[list[dict], dict[str, Any], list[dict], list[dict]]:
    """Two selected pages, one measurement and one mirroring evidence each."""
    manifest = sampling_manifest([ORIGIN, SECOND])
    measurements = [
        measurement(RUN_ID, "m-0001", ORIGIN),
        measurement(RUN_ID, "m-0002", SECOND),
    ]
    evidence = [
        evidence_for(measurements[0], "e-0001"),
        evidence_for(measurements[1], "e-0002"),
    ]
    records = [
        record(manifest, ORIGIN, "acq-0001", ["m-0001"]),
        record(manifest, SECOND, "acq-0002", ["m-0002"]),
    ]
    return records, manifest, measurements, evidence


def keys_of(found: Sequence[Any]) -> set[tuple[str, str]]:
    return {violation.key for violation in found}


def rules_in(found: Sequence[Any]) -> set[str]:
    return {violation.rule for violation in found}


# --- canaries on the fixtures themselves ----------------------------------------------------


def test_the_contract_registry_is_the_real_one() -> None:
    """Canary: the fixture validations below must run against the merged registry."""
    assert CONTRACTS.manifest_path.is_file()
    assert CONTRACTS.has_contract("sampling-manifest")
    assert CONTRACTS.has_contract("measurement-record")


def test_the_clean_fixture_is_contract_valid() -> None:
    """A red invariant test must never be explained by an invalid fixture."""
    _records, manifest, measurements, evidence = clean_set()
    assert CONTRACTS.validate("sampling-manifest", manifest) == ()
    for document in measurements:
        assert CONTRACTS.validate("measurement-record", document) == ()
    for document in evidence:
        assert CONTRACTS.validate("website-evidence", document) == ()


def test_the_h6_url_is_a_url_key_the_measurement_contract_cannot_carry() -> None:
    """Canary for C-PXAPI-020: without this the withheld case would be untestable."""
    assert len(H6_URL) == MAX_CONTRACT_URL_LENGTH
    assert CONTRACTS.validator_for_definition("url_key", shared="acquisition").is_valid(H6_URL)
    assert not CONTRACTS.validator_for_definition("url", shared="common").is_valid(H6_URL)


# --- the outcome vocabulary and the failure kinds it must express ---------------------------


def test_the_outcome_vocabulary_is_a_response_every_failure_kind_and_our_own_crash() -> None:
    """The set and its order, so a producer can map a kind by value and carry no table."""
    assert [outcome.value for outcome in AcquisitionOutcome] == [
        "RESPONSE_RECEIVED",
        *[kind.value for kind in FetchFailureKind],
        "RUNTIME_ERROR",
    ]


def test_every_fetch_failure_kind_is_expressible_as_an_outcome_by_its_own_value() -> None:
    assert [AcquisitionOutcome(kind.value).value for kind in FetchFailureKind] == [
        kind.value for kind in FetchFailureKind
    ]


def test_the_failure_kind_vocabulary_is_not_empty() -> None:
    """Canary: an empty port vocabulary would make both assertions above vacuous."""
    assert len(list(FetchFailureKind)) >= 7


def test_the_response_outcome_is_not_one_of_the_failure_kinds() -> None:
    """Canary against a tautology: the two extra tokens must really be extra."""
    kinds = {kind.value for kind in FetchFailureKind}
    assert "RESPONSE_RECEIVED" not in kinds
    assert "RUNTIME_ERROR" not in kinds


#: Words that would make an outcome token a statement about the page rather than about the
#: attempt. `INVALID` is deliberately absent: `INVALID_REDIRECT` is the fetcher's own inherited
#: token for a `Location` header we would not follow, which is a fact about our handling of a
#: transport artifact, and this vocabulary may not rename a port's token anyway.
PAGE_QUALITY_WORDS = ("BROKEN", "BAD", "POOR", "WEAK", "SLOW", "THIN", "QUALITY", "SEO")


def test_no_outcome_token_describes_the_website() -> None:
    """Every token names the transport or our own runtime, never a quality of the page."""
    offenders = [
        outcome.value
        for outcome in AcquisitionOutcome
        if any(word in outcome.value for word in PAGE_QUALITY_WORDS)
    ]
    assert offenders == []


def test_the_page_quality_word_scan_would_catch_a_planted_token() -> None:
    """Canary: a word list that matched nothing would make the rule above vacuous."""
    assert any(word in "BROKEN_PAGE" for word in PAGE_QUALITY_WORDS)
    assert not any(word in "RESPONSE_RECEIVED" for word in PAGE_QUALITY_WORDS)


# --- the HTTP status bounds ------------------------------------------------------------------


class _FakeSocket:
    def __init__(self, raw: bytes) -> None:
        self._raw = raw

    def makefile(self, *_args: Any, **_kwargs: Any) -> io.BytesIO:
        return io.BytesIO(self._raw)


def _status_read(code: int) -> int | str:
    """The status ``http.client`` reports for this status line, or the exception it raises."""
    response = http.client.HTTPResponse(_FakeSocket(f"HTTP/1.1 {code} X\r\n\r\n".encode()))  # type: ignore[arg-type]
    try:
        response.begin()
    except http.client.BadStatusLine as refused:
        return type(refused).__name__
    return response.status


def test_a_status_outside_the_bounds_is_refused_by_the_standard_library() -> None:
    """Derived, not chosen: `http.client` rejects a status line outside 100..999 outright."""
    assert _status_read(HTTP_STATUS_MIN - 1) == "BadStatusLine"
    assert _status_read(HTTP_STATUS_MAX + 1) == "BadStatusLine"


def test_the_upper_bound_is_reachable_and_is_carried_verbatim() -> None:
    """A narrower maximum — 599, say — would make a real 6xx..9xx response contract-invalid."""
    assert _status_read(HTTP_STATUS_MAX) == HTTP_STATUS_MAX
    assert _status_read(600) == 600
    assert _status_read(HTTP_STATUS_MIN + 1) == HTTP_STATUS_MIN + 1


def test_the_lower_bound_is_the_one_status_the_standard_library_treats_specially() -> None:
    """`HTTP_STATUS_MIN` is the parser's floor and `http.client`'s own CONTINUE constant.

    A bare `100 Continue` is consumed by `begin()`, which then reads the next response, so the
    lowest status a fetcher can actually carry is 101 and the contract's floor of 100 is a
    deliberate superset: no status line the standard library parses can be contract-invalid.
    """
    assert http.client.CONTINUE == HTTP_STATUS_MIN
    assert _status_read(HTTP_STATUS_MIN) == "RemoteDisconnected"
    assert issubclass(http.client.RemoteDisconnected, http.client.BadStatusLine)


def test_the_status_probe_reports_both_a_status_and_a_refusal() -> None:
    """Canary: a probe that always returned one answer would prove nothing above."""
    assert _status_read(200) == 200
    assert _status_read(99) == "BadStatusLine"


# --- is_contract_url ------------------------------------------------------------------------


def test_the_url_shape_is_the_contract_s_own_character_for_character() -> None:
    """Restated in the Domain because it may not import a validator; pinned so it cannot drift."""
    url = load_json(CONTRACTS.schema_path("common"))["$defs"]["url"]
    assert url["pattern"] == COMMON_URL_PATTERN
    assert url["maxLength"] == MAX_CONTRACT_URL_LENGTH


URL_TRUTH_TABLE: list[tuple[str, bool]] = [
    ("https://example.test/", True),
    ("http://example.test/", True),
    ("https://example.test/a b", False),
    ("HTTP://example.test/x", False),
    ("https://user:secret@example.test/", True),
    ("ftp://example.test/", False),
    ("/relative", False),
    (
        "https://example.test/" + "a" * (MAX_CONTRACT_URL_LENGTH - len("https://example.test/")),
        True,
    ),
    ("http://example.test/" + "a" * (MAX_CONTRACT_URL_LENGTH - len("http://example.test/")), False),
    (H6_URL, False),
]


@pytest.mark.parametrize(("value", "expected"), URL_TRUTH_TABLE, ids=lambda v: repr(v)[:40])
def test_is_contract_url_agrees_with_the_reference_validator(value: str, expected: bool) -> None:
    """The predicate and the validator must answer identically on every value."""
    validator = CONTRACTS.validator_for_definition("url", shared="common")
    assert is_contract_url(value) is expected
    assert validator.is_valid(value) is expected


def test_the_truth_table_exercises_both_answers() -> None:
    """Canary: a table of one answer would let a constant predicate pass."""
    answers = {expected for _value, expected in URL_TRUTH_TABLE}
    assert answers == {True, False}


@pytest.mark.parametrize("value", [None, 200, b"https://example.test/", ["x"], {}])
def test_is_contract_url_refuses_anything_that_is_not_a_string(value: Any) -> None:
    assert is_contract_url(value) is False


# --- body_digest ----------------------------------------------------------------------------


@pytest.mark.parametrize("body", [b"", b"<html></html>", bytes(range(256))])
def test_body_digest_is_the_algorithm_prefixed_sha256_of_those_exact_bytes(body: bytes) -> None:
    assert body_digest(body) == "sha256:" + hashlib.sha256(body).hexdigest()
    assert CONTRACTS.validator_for_definition("digest", shared="acquisition").is_valid(
        body_digest(body)
    )


def test_body_digest_is_deterministic_for_identical_bytes_and_changes_for_one_byte() -> None:
    assert body_digest(b"<html>a</html>") == body_digest(b"<html>a</html>")
    assert body_digest(b"<html>a</html>") != body_digest(b"<html>b</html>")


def test_body_digest_is_computed_over_the_body_and_nothing_else() -> None:
    """A digest over a JSON rendering, or over the URL as well, would not be this value."""
    assert body_digest(b'"abc"') != body_digest(b"abc")
    assert body_digest(b"abc") != body_digest(b"https://example.test/abc")


# --- withheld_reason_for ---------------------------------------------------------------------


WITHHELD_CASES: list[tuple[str, str | None, str | None]] = [
    (ORIGIN, ORIGIN, None),
    (ORIGIN, None, None),
    (H6_URL, None, MEASUREMENTS_WITHHELD_SOURCE_URL),
    (H6_URL, ORIGIN, MEASUREMENTS_WITHHELD_SOURCE_URL),
    (ORIGIN, H6_URL, MEASUREMENTS_WITHHELD_SOURCE_URL),
    (ORIGIN, "https://example.test/x#a b", MEASUREMENTS_WITHHELD_SOURCE_URL),
]


@pytest.mark.parametrize(("url_key", "final_url", "expected"), WITHHELD_CASES)
def test_withheld_reason_names_an_unrepresentable_source_url_and_nothing_else(
    url_key: str, final_url: str | None, expected: str | None
) -> None:
    assert withheld_reason_for(url_key, final_url) == expected


def test_the_withheld_cases_exercise_both_answers() -> None:
    """Canary: a table of one answer would let a constant function pass."""
    assert {expected for *_head, expected in WITHHELD_CASES} == {
        None,
        MEASUREMENTS_WITHHELD_SOURCE_URL,
    }


# --- the producer invariants -----------------------------------------------------------------


def test_a_clean_acquisition_set_violates_nothing() -> None:
    records, manifest, measurements, evidence = clean_set()
    assert acquisition_violations(records, manifest, measurements, evidence) == ()


def test_require_emittable_acquisition_accepts_a_clean_set() -> None:
    assert require_emittable_acquisition(*clean_set()) is None


def _drop_second_record(state: tuple) -> tuple:
    records, manifest, measurements, evidence = state
    return records[:1], manifest, measurements[:1], evidence[:1]


def _foreign_manifest_digest(state: tuple) -> tuple:
    records, manifest, measurements, evidence = state
    records[1]["sampling_manifest_output_digest"] = "sha256:" + "f" * 64
    return records, manifest, measurements, evidence


def _foreign_observation_mode(state: tuple) -> tuple:
    records, manifest, measurements, evidence = state
    records[0]["observation_mode"] = "RENDERED_BROWSER"
    return records, manifest, measurements, evidence


def _repeat_acquisition_id(state: tuple) -> tuple:
    records, manifest, measurements, evidence = state
    records[1]["acquisition_id"] = records[0]["acquisition_id"]
    return records, manifest, measurements, evidence


def _share_one_measurement(state: tuple) -> tuple:
    records, manifest, measurements, evidence = state
    records[1]["measurement_refs"].extend(records[0]["measurement_refs"])
    return records, manifest, measurements, evidence


def _orphan_measurement(state: tuple) -> tuple:
    records, manifest, measurements, evidence = state
    measurements.append(measurement(RUN_ID, "m-0003", SECOND))
    return records, manifest, measurements, evidence


def _ref_an_absent_measurement(state: tuple) -> tuple:
    records, manifest, measurements, evidence = state
    records[1]["measurement_refs"].append("m-9999")
    return records, manifest, measurements, evidence


def _empty_refs_without_a_reason(state: tuple) -> tuple:
    records, manifest, measurements, evidence = state
    records[1]["measurement_refs"] = []
    measurements.pop()
    evidence.pop()
    return records, manifest, measurements, evidence


def _evidence_across_two_pages(state: tuple) -> tuple:
    records, manifest, measurements, evidence = state
    evidence[0]["measurement_refs"] = ["m-0001", "m-0002"]
    evidence.pop()
    return records, manifest, measurements, evidence


def _evidence_carries_a_polarity(state: tuple) -> tuple:
    records, manifest, measurements, evidence = state
    evidence[1]["polarity"] = "NEGATIVE"
    return records, manifest, measurements, evidence


def _emit_a_raw_artifact_ref(state: tuple) -> tuple:
    records, manifest, measurements, evidence = state
    records[0]["raw_artifact_ref"] = "artifact-0001"
    return records, manifest, measurements, evidence


#: ``rule -> (mutation, expected pointer)``. Each mutation must make exactly its own rule fire.
COUNTEREXAMPLES: dict[str, tuple[Callable[[tuple], tuple], str]] = {
    "one_record_per_selection": (_drop_second_record, RECORDS_POINTER),
    "record_binds_manifest": (_foreign_manifest_digest, f"{RECORDS_POINTER}/1"),
    "record_declares_this_producer": (_foreign_observation_mode, f"{RECORDS_POINTER}/0"),
    "unique_acquisition_id": (_repeat_acquisition_id, f"{RECORDS_POINTER}/1"),
    "measurement_owned_once": (_share_one_measurement, f"{RECORDS_POINTER}/1"),
    "every_measurement_is_owned": (_orphan_measurement, "/measurements/2"),
    "refs_name_a_measurement": (_ref_an_absent_measurement, f"{RECORDS_POINTER}/1"),
    "refs_empty_iff_withheld": (_empty_refs_without_a_reason, f"{RECORDS_POINTER}/1"),
    "evidence_within_one_page": (_evidence_across_two_pages, "/website_evidence/0"),
    "no_polarity_on_page_evidence": (_evidence_carries_a_polarity, "/website_evidence/1"),
    "raw_artifact_ref_absent": (_emit_a_raw_artifact_ref, f"{RECORDS_POINTER}/0"),
}


@pytest.mark.parametrize("rule", sorted(COUNTEREXAMPLES), ids=sorted(COUNTEREXAMPLES))
def test_each_counterexample_fires_exactly_its_own_rule(rule: str) -> None:
    mutate, pointer = COUNTEREXAMPLES[rule]
    found = acquisition_violations(*mutate(clean_set()))
    assert rules_in(found) == {rule}, sorted(keys_of(found))
    assert (pointer, rule) in keys_of(found)


@pytest.mark.parametrize("rule", sorted(COUNTEREXAMPLES), ids=sorted(COUNTEREXAMPLES))
def test_each_counterexample_raises_and_withholds_the_documents(rule: str) -> None:
    mutate, _pointer = COUNTEREXAMPLES[rule]
    with pytest.raises(ProducerInvariantViolated) as info:
        require_emittable_acquisition(*mutate(clean_set()))
    assert info.value.contract == PAGE_ACQUISITION_RECORD
    assert {key[1] for key in info.value.keys} == {rule}


def test_every_declared_rule_has_a_counterexample() -> None:
    """A rule nobody can make fire is a rule that proves nothing."""
    assert set(PRODUCER_RULES) == set(COUNTEREXAMPLES)


def test_every_declared_rule_states_what_it_guarantees() -> None:
    for rule, meaning in PRODUCER_RULES.items():
        assert meaning.strip(), rule


def test_the_rule_names_are_stable_tokens_and_not_free_text() -> None:
    """An expectation recording a sentence would go red on a rewording."""
    for rule in PRODUCER_RULES:
        assert rule == rule.strip().lower()
        assert " " not in rule


def test_the_record_order_is_the_selection_rank_order_and_not_merely_the_set() -> None:
    """Re-serialising the pages in another sequence is a different acquisition, not the same one."""
    records, manifest, measurements, evidence = clean_set()
    reordered = [records[1], records[0]]
    found = acquisition_violations(reordered, manifest, measurements, evidence)
    assert rules_in(found) == {"one_record_per_selection"}


def test_a_withheld_page_is_accepted_when_it_states_its_reason() -> None:
    """The one legal shape with no measurements at all: C-PXAPI-020 contained per page."""
    records, manifest, measurements, evidence = clean_set()
    records[1]["measurement_refs"] = []
    records[1]["measurements_withheld_reason"] = MEASUREMENTS_WITHHELD_SOURCE_URL
    measurements.pop()
    evidence.pop()
    assert acquisition_violations(records, manifest, measurements, evidence) == ()
