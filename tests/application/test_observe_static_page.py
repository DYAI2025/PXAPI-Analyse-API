"""The generic static-page observer: page-scoped facts, and no homepage semantics anywhere.

Every document these tests produce is validated against the merged contracts through the same
registry the service uses, so "it validates" here means what it means in production. Above that,
three properties are asserted that no schema can assert on its own.

**It is generic.** Not one metric id, collector token or scenario token in the emitted documents
is homepage-specific, on the success path or on the failure path, and the combined
`HOMEPAGE_GENERIC_NOINDEX_PRESENT` record the homepage use case emits is absent. The observer
does not import `AnalyzeHomepage` and emits no `DiagnosticFinding`.

**It never lets site-controlled input become a false statement.** A canonical link the page
declares is resolved strictly: a value the URL parser refuses, and a value the measurement
contract cannot carry, both become UNKNOWN while the presence fact stays KNOWN. A page whose own
identity or final URL is unrepresentable yields no measurements at all and says so, instead of
emitting documents its own registry would reject. And a truncated read never becomes absence.

**It is deterministic.** One frozen input produces the same documents on every run, and two runs
with different identities produce the same semantics.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from pxapi.adapters.contracts.registry import ContractRegistry
from pxapi.adapters.web.html_observations import read_html
from pxapi.application.observe_static_page import (
    HTML_METRICS,
    NON_SUCCESS_NOT_ASSESSED,
    NOT_ASSESSED_FOR,
    PAGE_METRICS,
    SCENARIO_SELECTED_PAGE_STATIC_FETCH,
    STATIC_PAGE_COLLECTOR,
    STATIC_PAGE_COLLECTOR_VERSION,
    DocumentStatus,
    StaticPageObserver,
)
from pxapi.config.contract_root import contract_root
from pxapi.domain.observations import Metric
from pxapi.domain.page_acquisition import MEASUREMENTS_WITHHELD_SOURCE_URL
from pxapi.ports.html_observation import HtmlUnreadable
from pxapi.ports.page_fetch import FetchFailureKind, PageFetchFailure, PageFetchOutcome

CONTRACTS = ContractRegistry(contract_root())

RUN_ID = "run-0001"
PAGE = "https://example.test/leistungen"
OBSERVED_AT = "2026-09-19T10:00:01Z"
HTML_CONTENT_TYPE = "text/html; charset=utf-8"

#: Keys that would make an emitted document a judgement rather than an observation.
VERDICT_KEYS = frozenset(
    {
        "polarity",
        "score",
        "severity",
        "confidence",
        "finding",
        "finding_summary",
        "rule_id",
        "business_impact",
        "intervention_level",
        "quality",
        "rating",
        "weight",
    }
)

#: A url_key `acquisition#/$defs/url_key` admits and `common#/$defs/url` refuses. C-PXAPI-020.
_HOST = "a" * (250 - len(".example.test")) + ".example.test"
_BASE = f"http://{_HOST}/"
UNREPRESENTABLE = _BASE + "b" * (2048 - len(_BASE))


def page_body(canonical: str | None = None, title: str = "Leistungen") -> bytes:
    link = f'<link rel="canonical" href="{canonical}">' if canonical is not None else ""
    return (
        f"<!doctype html><html><head><title>{title}</title>"
        f'<meta name="description" content="Was wir fuer Sie tun.">'
        f"{link}</head><body>...</body></html>"
    ).encode()


def response(
    final_url: str = PAGE,
    body: bytes | None = None,
    status: int = 200,
    content_type: str | None = HTML_CONTENT_TYPE,
    truncated: bool = False,
    undecodable: bool = False,
    redirect_count: int = 0,
    x_robots_tag: tuple[str, ...] = (),
) -> PageFetchOutcome:
    return PageFetchOutcome(
        final_url=final_url,
        status_code=status,
        content_type=content_type,
        x_robots_tag=x_robots_tag,
        is_https=final_url.startswith("https://"),
        redirect_count=redirect_count,
        body=page_body() if body is None else body,
        truncated=truncated,
        declared_charset="utf-8",
        undecodable=undecodable,
    )


def counting_ids(prefix: str = "id"):
    counter = {"n": 0}

    def new_id() -> str:
        counter["n"] += 1
        return f"{prefix}-{counter['n']:04d}"

    return new_id


def observer(read=read_html, prefix: str = "id") -> StaticPageObserver:
    return StaticPageObserver(
        read_html=read,
        new_id=counting_ids(prefix),
        max_text_length=CONTRACTS.max_single_line_text(),
    )


def observe(result: Any, url_key: str = PAGE, read=read_html, prefix: str = "id"):
    return observer(read=read, prefix=prefix).observe(RUN_ID, url_key, result, OBSERVED_AT)


def by_metric(observation: Any) -> dict[str, dict[str, Any]]:
    return {record["metric_id"]: record for record in observation.measurements}


def state_of(record: dict[str, Any]) -> str | None:
    return record["assessment"].get("result_state")


def reason_of(record: dict[str, Any]) -> str | None:
    return record["assessment"].get("not_assessed_reason")


def assert_documents_validate(observation: Any) -> None:
    for record in observation.measurements:
        found = CONTRACTS.validate("measurement-record", record)
        assert found == (), f"{record['metric_id']}: {[v.key for v in found]}"
    for item in observation.evidence:
        found = CONTRACTS.validate("website-evidence", item)
        assert found == (), f"{item['evidence_id']}: {[v.key for v in found]}"


def keys_anywhere(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for item in value.values() for k in keys_anywhere(item)}
    if isinstance(value, list):
        return {k for item in value for k in keys_anywhere(item)}
    return set()


# --- canaries --------------------------------------------------------------------------------


def test_the_contract_registry_is_the_real_one() -> None:
    assert CONTRACTS.manifest_path.is_file()
    assert CONTRACTS.has_contract("measurement-record")
    assert CONTRACTS.max_single_line_text() == 500


def test_the_verdict_key_scan_finds_a_planted_key() -> None:
    """Canary: a scan that saw nothing would make every neutrality assertion below vacuous."""
    assert keys_anywhere({"a": [{"polarity": "NEGATIVE"}]}) & VERDICT_KEYS == {"polarity"}


# --- it is generic ----------------------------------------------------------------------------


def test_the_page_profile_emits_thirteen_metrics_and_no_homepage_token() -> None:
    observation = observe(response())
    assert len(observation.measurements) == len(PAGE_METRICS) == 13
    assert {record["metric_id"] for record in observation.measurements} == {
        metric.value for metric in PAGE_METRICS
    }
    assert Metric.HOMEPAGE_GENERIC_NOINDEX_PRESENT.value not in by_metric(observation)
    assert not any("HOMEPAGE" in metric.value for metric in PAGE_METRICS)


def test_the_failure_path_emits_the_same_thirteen_metrics_and_no_homepage_token() -> None:
    observation = observe(PageFetchFailure(FetchFailureKind.TIMEOUT))
    assert len(observation.measurements) == 13
    assert Metric.HOMEPAGE_GENERIC_NOINDEX_PRESENT.value not in by_metric(observation)


def test_the_page_metrics_are_a_proper_subset_of_the_homepage_ones() -> None:
    """The profile reuses the existing vocabulary and invents no new metric id."""
    from pxapi.application.analyze_homepage import ALL_METRICS

    assert set(PAGE_METRICS) < set(ALL_METRICS)
    assert set(ALL_METRICS) - set(PAGE_METRICS) == {Metric.HOMEPAGE_GENERIC_NOINDEX_PRESENT}


def test_every_document_names_the_page_collector_and_the_page_scenario() -> None:
    observation = observe(response())
    for record in observation.measurements:
        assert record["collector"] == STATIC_PAGE_COLLECTOR
        assert record["collector_version"] == STATIC_PAGE_COLLECTOR_VERSION
    for item in observation.evidence:
        assert item["scenario"] == SCENARIO_SELECTED_PAGE_STATIC_FETCH
        assert item["collector"] == STATIC_PAGE_COLLECTOR
    assert "HOMEPAGE" not in SCENARIO_SELECTED_PAGE_STATIC_FETCH
    assert "HOMEPAGE" not in STATIC_PAGE_COLLECTOR


def test_the_observer_module_does_not_import_the_homepage_use_case() -> None:
    """Small intentional duplication, per D-20-E: the shipped homepage path is not in scope."""
    import ast
    import inspect

    import pxapi.application.observe_static_page as module

    tree = ast.parse(inspect.getsource(module))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0
    }
    assert "pxapi.application.analyze_homepage" not in imported
    assert not any(name.startswith("pxapi.application.") for name in imported), sorted(imported)


def test_no_emitted_document_carries_a_verdict_key() -> None:
    for result in (response(status=503), response(), PageFetchFailure(FetchFailureKind.TIMEOUT)):
        observation = observe(result)
        found = keys_anywhere(
            {"m": list(observation.measurements), "e": list(observation.evidence)}
        )
        assert found & VERDICT_KEYS == set()


def test_the_observation_carries_no_findings_member_at_all() -> None:
    import dataclasses

    observation = observe(response())
    names = {field.name for field in dataclasses.fields(observation)}
    assert names == {"measurements", "evidence", "document_status", "withheld_reason"}


# --- a valid page ------------------------------------------------------------------------------


def test_a_valid_page_produces_contract_valid_measurements_and_evidence() -> None:
    observation = observe(response())
    assert_documents_validate(observation)
    assert observation.document_status is DocumentStatus.READ
    assert observation.withheld_reason is None
    facts = by_metric(observation)
    assert facts[Metric.HTTP_STATUS.value]["result"]["integer_value"] == 200
    assert facts[Metric.PAGE_TITLE.value]["result"]["text_value"] == "Leistungen"
    assert facts[Metric.TRANSPORT_IS_HTTPS.value]["result"]["boolean_value"] is True


def test_each_measurement_is_mirrored_by_exactly_one_evidence_document() -> None:
    observation = observe(response())
    assert len(observation.evidence) == len(observation.measurements)
    refs = [item["measurement_refs"] for item in observation.evidence]
    assert refs == [[record["measurement_id"]] for record in observation.measurements]
    for record, item in zip(observation.measurements, observation.evidence, strict=True):
        assert item["assessment"] == record["assessment"]
        assert item["source_url"] == record["source_url"]
        assert item["observed_at"] == record["observed_at"]
        assert "polarity" not in item


def test_every_identity_is_issued_for_the_measurements_before_the_evidence() -> None:
    """Determinism: the id order is part of what a frozen input reproduces."""
    observation = observe(response())
    assert [record["measurement_id"] for record in observation.measurements] == [
        f"id-{index:04d}" for index in range(1, 14)
    ]
    assert [item["evidence_id"] for item in observation.evidence] == [
        f"id-{index:04d}" for index in range(14, 27)
    ]


def test_the_source_url_rule_puts_path_outcomes_at_the_requested_identity() -> None:
    observation = observe(response(final_url="https://example.test/leistungen/", redirect_count=1))
    facts = by_metric(observation)
    assert facts[Metric.FINAL_URL.value]["source_url"] == PAGE
    assert facts[Metric.REDIRECT_COUNT.value]["source_url"] == PAGE
    assert facts[Metric.PAGE_TITLE.value]["source_url"] == "https://example.test/leistungen/"
    assert facts[Metric.FINAL_URL.value]["result"]["url_value"] == (
        "https://example.test/leistungen/"
    )


def test_a_non_2xx_response_is_measured_and_judged_by_nothing() -> None:
    observation = observe(response(status=503))
    facts = by_metric(observation)
    assert facts[Metric.HTTP_STATUS.value]["result"]["integer_value"] == 503
    assert state_of(facts[Metric.HTTP_STATUS.value]) == "KNOWN"
    assert_documents_validate(observation)


@pytest.mark.parametrize("status", [301, 404, 500, 503])
def test_a_non_2xx_error_document_is_never_parsed_as_page_content(status: int) -> None:
    """PXAPI-20.B, D-20-F: the title of an error template is not the selected page's title."""
    calls: list[bytes] = []

    def spy(body: bytes, _charset: str | None = None):
        calls.append(body)
        return read_html(body)

    observation = observe(response(status=status, body=page_body(title="Fehler")), read=spy)
    facts = by_metric(observation)
    assert calls == []
    assert observation.document_status is DocumentStatus.NON_SUCCESS_STATUS
    for metric in (*HTML_METRICS, Metric.META_ROBOTS_GENERIC_NOINDEX_PRESENT):
        assert reason_of(facts[metric.value]) == NON_SUCCESS_NOT_ASSESSED
    assert state_of(facts[Metric.X_ROBOTS_TAG_GENERIC_NOINDEX_PRESENT.value]) == "KNOWN"
    assert len(observation.measurements) == len(PAGE_METRICS)
    assert_documents_validate(observation)


def test_a_2xx_response_is_still_read_as_page_content() -> None:
    """Canary: the success range is not accidentally empty."""
    facts = by_metric(observe(response(status=204)))
    assert facts[Metric.PAGE_TITLE.value]["result"]["text_value"] == "Leistungen"


def test_a_runtime_error_observation_is_neutral_for_every_metric() -> None:
    observation = observer().observe_runtime_error(RUN_ID, PAGE, OBSERVED_AT)
    assert observation.document_status is DocumentStatus.NO_RESPONSE
    assert [m["metric_id"] for m in observation.measurements] == [m.value for m in PAGE_METRICS]
    assert {reason_of(m) for m in observation.measurements} == {"RUNTIME_ERROR"}
    assert_documents_validate(observation)


def test_a_runtime_error_on_an_unrepresentable_identity_is_withheld() -> None:
    observation = observer().observe_runtime_error(RUN_ID, UNREPRESENTABLE, OBSERVED_AT)
    assert observation.measurements == () and observation.evidence == ()
    assert observation.withheld_reason == MEASUREMENTS_WITHHELD_SOURCE_URL


# --- site-controlled canonical links -----------------------------------------------------------

#: `(canonical the page declares, whether its value is representable)`. The first four are the
#: classes measured on this base as C-PXAPI-018; the last two are representable and must stay so.
CANONICAL_CASES: list[tuple[str, bool]] = [
    ("/a b", False),
    ("http://[", False),
    ("HTTP://example.test/x", False),
    ("https://example.test/" + "a" * (2049 - len("https://example.test/")), False),
    ("https://example.test/kanonisch", True),
    ("/relativ/aber/gut", True),
]


@pytest.mark.parametrize(("canonical", "representable"), CANONICAL_CASES, ids=lambda v: str(v)[:30])
def test_a_site_declared_canonical_never_produces_an_invalid_document(
    canonical: str, representable: bool
) -> None:
    observation = observe(response(body=page_body(canonical)))
    assert_documents_validate(observation)
    facts = by_metric(observation)
    present = facts[Metric.CANONICAL_PRESENT.value]
    value = facts[Metric.CANONICAL_URL.value]
    assert state_of(present) == "KNOWN"
    assert present["result"]["boolean_value"] is True, "presence is a fact the value cannot undo"
    assert state_of(value) == ("KNOWN" if representable else "UNKNOWN")
    assert ("result" in value) is representable


def test_the_canonical_table_exercises_both_answers() -> None:
    """Canary: a table of one answer would let a constant branch pass."""
    assert {representable for _canonical, representable in CANONICAL_CASES} == {True, False}


def test_a_canonical_longer_than_the_text_bound_but_within_the_url_bound_is_known() -> None:
    """Deliberate divergence from the homepage path, recorded in the 20.A evidence document.

    The homepage use case gates every value on the 500-character `single_line_text` bound, so a
    600-character canonical is recorded UNKNOWN there. A URL value is carried by `common url`,
    whose bound is 2048, so recording UNKNOWN for a value the contract can hold would be a false
    UNKNOWN — the class of defect this repository exists to prevent.
    """
    long_canonical = "https://example.test/" + "a" * (600 - len("https://example.test/"))
    assert len(long_canonical) == 600
    observation = observe(response(body=page_body(long_canonical)))
    value = by_metric(observation)[Metric.CANONICAL_URL.value]
    assert state_of(value) == "KNOWN"
    assert value["result"]["url_value"] == long_canonical
    assert_documents_validate(observation)


def test_a_declared_canonical_is_resolved_against_the_final_url() -> None:
    observation = observe(response(final_url="https://example.test/a/b", body=page_body("../c")))
    value = by_metric(observation)[Metric.CANONICAL_URL.value]
    assert value["result"]["url_value"] == "https://example.test/c"


# --- the page's own identity is unrepresentable -------------------------------------------------


@pytest.mark.parametrize(
    ("url_key", "final_url"),
    [(UNREPRESENTABLE, UNREPRESENTABLE), (PAGE, UNREPRESENTABLE), (UNREPRESENTABLE, PAGE)],
    ids=["both", "final-only", "key-only"],
)
def test_a_page_whose_urls_are_unrepresentable_yields_no_documents_and_says_why(
    url_key: str, final_url: str
) -> None:
    observation = observe(response(final_url=final_url), url_key=url_key)
    assert observation.measurements == ()
    assert observation.evidence == ()
    assert observation.document_status is DocumentStatus.WITHHELD
    assert observation.withheld_reason == MEASUREMENTS_WITHHELD_SOURCE_URL


def test_a_failure_on_an_unrepresentable_identity_is_also_withheld() -> None:
    observation = observe(PageFetchFailure(FetchFailureKind.TIMEOUT), url_key=UNREPRESENTABLE)
    assert observation.measurements == ()
    assert observation.withheld_reason == MEASUREMENTS_WITHHELD_SOURCE_URL


def test_a_representable_page_is_not_withheld() -> None:
    """Canary: a withhold rule that fired always would empty every page."""
    assert observe(response()).withheld_reason is None


# --- neutral technical outcomes ------------------------------------------------------------------


@pytest.mark.parametrize("kind", list(FetchFailureKind), ids=lambda k: k.value)
def test_a_fetch_failure_is_neutral_for_every_metric(kind: FetchFailureKind) -> None:
    observation = observe(PageFetchFailure(kind))
    assert_documents_validate(observation)
    assert observation.document_status is DocumentStatus.NO_RESPONSE
    for record in observation.measurements:
        assert reason_of(record) == NOT_ASSESSED_FOR[kind]
        assert "result" not in record
        assert record["source_url"] == PAGE
    assert all("polarity" not in item for item in observation.evidence)


def test_the_failure_mapping_is_exhaustive_over_the_port_vocabulary() -> None:
    assert set(NOT_ASSESSED_FOR) == set(FetchFailureKind)
    assert len(NOT_ASSESSED_FOR) >= 7


def test_a_non_html_response_makes_the_document_metrics_not_applicable() -> None:
    observation = observe(response(content_type="application/pdf", body=b"%PDF-1.7"))
    assert_documents_validate(observation)
    assert observation.document_status is DocumentStatus.NOT_A_DOCUMENT
    facts = by_metric(observation)
    for metric in (Metric.PAGE_TITLE_PRESENT, Metric.PAGE_TITLE, Metric.CANONICAL_URL):
        assert state_of(facts[metric.value]) == "NOT_APPLICABLE"
    assert state_of(facts[Metric.HTTP_STATUS.value]) == "KNOWN"


def test_an_undecodable_response_is_our_runtime_and_never_an_absence() -> None:
    observation = observe(response(body=b"", undecodable=True))
    assert_documents_validate(observation)
    assert observation.document_status is DocumentStatus.UNREADABLE
    facts = by_metric(observation)
    assert reason_of(facts[Metric.PAGE_TITLE_PRESENT.value]) == "RUNTIME_ERROR"
    assert "result" not in facts[Metric.PAGE_TITLE_PRESENT.value]


def test_a_parser_failure_is_our_runtime_and_never_an_absence() -> None:
    def raising(_body: bytes, _charset: str | None = None):
        raise HtmlUnreadable("planted")

    observation = observe(response(), read=raising)
    assert_documents_validate(observation)
    assert observation.document_status is DocumentStatus.UNREADABLE
    facts = by_metric(observation)
    assert reason_of(facts[Metric.META_DESCRIPTION.value]) == "RUNTIME_ERROR"
    assert state_of(facts[Metric.HTTP_STATUS.value]) == "KNOWN", "transport facts survive"


def test_an_undecodable_response_is_never_handed_to_the_parser() -> None:
    calls: list[bytes] = []

    def spy(body: bytes, _charset: str | None = None):
        calls.append(body)
        return read_html(body)

    observe(response(body=b"", undecodable=True), read=spy)
    assert calls == []
    observe(response(), read=spy)
    assert len(calls) == 1


def test_a_truncated_read_never_becomes_a_false_absence() -> None:
    observation = observe(response(body=b"<!doctype html><html><head>", truncated=True))
    assert_documents_validate(observation)
    facts = by_metric(observation)
    present = facts[Metric.PAGE_TITLE_PRESENT.value]
    assert state_of(present) == "UNKNOWN"
    assert "result" not in present, "an element we never read is not absent"
    assert state_of(facts[Metric.PAGE_TITLE.value]) == "UNKNOWN"


def test_a_truncated_read_still_reports_what_it_did_see() -> None:
    observation = observe(response(body=page_body(), truncated=True))
    facts = by_metric(observation)
    assert facts[Metric.PAGE_TITLE.value]["result"]["text_value"] == "Leistungen"


def test_a_title_beyond_the_text_bound_establishes_nothing_rather_than_a_shortened_value() -> None:
    long_title = "t" * (CONTRACTS.max_single_line_text() + 1)
    observation = observe(response(body=page_body(title=long_title)))
    facts = by_metric(observation)
    assert facts[Metric.PAGE_TITLE_PRESENT.value]["result"]["boolean_value"] is True
    assert state_of(facts[Metric.PAGE_TITLE.value]) == "UNKNOWN"
    assert_documents_validate(observation)


def test_a_truncated_read_withholds_the_meta_robots_channel_but_keeps_a_seen_directive() -> None:
    absent = observe(response(body=b"<!doctype html><html><head>", truncated=True))
    assert state_of(by_metric(absent)[Metric.META_ROBOTS_GENERIC_NOINDEX_PRESENT.value]) == (
        "UNKNOWN"
    )
    seen = observe(
        response(body=b'<html><head><meta name="robots" content="noindex"></head>', truncated=True)
    )
    directive = by_metric(seen)[Metric.META_ROBOTS_GENERIC_NOINDEX_PRESENT.value]
    assert directive["result"]["boolean_value"] is True


def test_the_header_channel_is_assessable_even_for_a_non_document() -> None:
    observation = observe(
        response(content_type="application/pdf", body=b"%PDF", x_robots_tag=("noindex",))
    )
    facts = by_metric(observation)
    assert facts[Metric.X_ROBOTS_TAG_GENERIC_NOINDEX_PRESENT.value]["result"]["boolean_value"]
    assert state_of(facts[Metric.META_ROBOTS_GENERIC_NOINDEX_PRESENT.value]) == "NOT_APPLICABLE"


# --- determinism ---------------------------------------------------------------------------------


def identity_free(observation: Any) -> Any:
    """The observation with every identity removed, so two runs can be compared semantically."""
    documents = copy.deepcopy(
        {"m": list(observation.measurements), "e": list(observation.evidence)}
    )
    for record in documents["m"]:
        record.pop("measurement_id")
    for item in documents["e"]:
        item.pop("evidence_id")
        item.pop("measurement_refs")
    return documents


def test_one_frozen_input_produces_byte_identical_documents_on_every_run() -> None:
    first = observe(response(body=page_body("https://example.test/k")))
    second = observe(response(body=page_body("https://example.test/k")))
    assert list(first.measurements) == list(second.measurements)
    assert list(first.evidence) == list(second.evidence)


def test_different_identities_leave_the_semantics_identical() -> None:
    first = observe(response(), prefix="one")
    second = observe(response(), prefix="two")
    assert identity_free(first) == identity_free(second)
    assert first.measurements[0]["measurement_id"] != second.measurements[0]["measurement_id"]


def test_the_identity_free_projection_still_carries_the_facts() -> None:
    """Canary: a projection that dropped everything would make the comparison above vacuous."""
    projected = identity_free(observe(response()))
    assert len(projected["m"]) == 13
    assert any("result" in record for record in projected["m"])
