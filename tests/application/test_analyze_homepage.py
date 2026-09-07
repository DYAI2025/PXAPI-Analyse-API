"""The whole path, and the rule it exists to enforce.

Every document these tests produce is validated against the **merged** contracts through the
same registry the service uses, so "it validates" here means the same thing it means in
production. Above that, the tests assert the property no schema can assert on its own: that a
timeout, a DNS failure, a blocked target or a broken parser produces no statement about the
website at all.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pxapi.adapters.contracts.registry import ContractRegistry
from pxapi.adapters.web.html_observations import read_html
from pxapi.adapters.web.page_fetcher import SafePageFetcher
from pxapi.application.analyze_homepage import AnalyzeHomepage
from pxapi.config.contract_root import contract_root
from pxapi.config.fetch_limits import FetchLimits
from pxapi.domain.observations import Metric
from pxapi.ports.html_observation import HtmlUnreadable
from pxapi.ports.page_fetch import FetchFailureKind, PageFetchFailure
from tests.adapters.http_test_server import ControlledHttpServer, Route, loopback_policy

CONTRACTS = ContractRegistry(contract_root())

HTML_HEADERS = {"Content-Type": "text/html; charset=utf-8"}
FULL_PAGE = (
    b"<!doctype html><html><head>"
    b"<title>Example Domain</title>"
    b'<meta name="description" content="A page used for examples.">'
    b'<link rel="canonical" href="https://example.test/home">'
    b"</head><body>hello</body></html>"
)

#: Which contract each envelope member must validate against.
MEMBER_CONTRACT = {
    "analysis_run_request": "analysis-run-request",
    "analysis_run_state": "analysis-run-state",
    "stage_executions": "stage-execution-record",
    "measurements": "measurement-record",
    "website_evidence": "website-evidence",
}


def request_for(url: str) -> dict:
    return {
        "schema_version": "1.0.0",
        "run_id": "run-0001",
        "request_id": "req-0001",
        "requested_at": "2026-09-07T10:00:00Z",
        "target_url": url,
        "scan_mode": "PUBLIC_NON_INVASIVE",
    }


def frozen_clock():
    moment = datetime(2026, 9, 7, 10, 0, 0, tzinfo=UTC)
    counter = {"n": 0}

    def clock() -> datetime:
        counter["n"] += 1
        return moment + timedelta(seconds=counter["n"])

    return clock


def counting_ids():
    counter = {"n": 0}

    def new_id() -> str:
        counter["n"] += 1
        return f"id-{counter['n']:04d}"

    return new_id


def use_case(fetcher, read=read_html) -> AnalyzeHomepage:
    return AnalyzeHomepage(
        fetcher=fetcher,
        read_html=read,
        clock=frozen_clock(),
        new_id=counting_ids(),
        max_text_length=CONTRACTS.max_single_line_text(),
    )


class StubFetcher:
    def __init__(self, result):
        self.result = result

    def fetch(self, url: str):
        return self.result


def analyse(routes: dict[str, Route], path: str = "/", **limits) -> dict:
    with ControlledHttpServer(routes) as server:
        fetcher = SafePageFetcher(
            policy=loopback_policy(), limits=FetchLimits(**limits) if limits else FetchLimits()
        )
        return use_case(fetcher).run(request_for(server.url(path)))


# --- every document validates against the merged contracts -------------------------------


def assert_envelope_validates(envelope: dict) -> None:
    for member, contract in MEMBER_CONTRACT.items():
        value = envelope[member]
        documents = value if isinstance(value, list) else [value]
        for document in documents:
            found = CONTRACTS.validate(contract, document)
            assert found == (), f"{member}: {[v.key for v in found]}"


def measurements_by_metric(envelope: dict) -> dict[str, dict]:
    return {m["metric_id"]: m for m in envelope["measurements"]}


def test_the_contract_registry_is_the_real_one() -> None:
    """Canary: these tests must validate against the merged registry, not an empty one."""
    assert CONTRACTS.manifest_path.is_file()
    assert "measurement-record" in CONTRACTS.names()
    assert CONTRACTS.max_single_line_text() == 500


def test_a_real_response_produces_a_fully_valid_envelope() -> None:
    envelope = analyse({"/": Route(body=FULL_PAGE, headers=HTML_HEADERS)})
    assert_envelope_validates(envelope)


def test_at_least_three_distinct_facts_come_from_the_real_response() -> None:
    """The acceptance criterion: real bytes on the wire become real, referenced facts."""
    envelope = analyse({"/": Route(body=FULL_PAGE, headers=HTML_HEADERS)})
    found = measurements_by_metric(envelope)

    assert found[Metric.HTTP_STATUS]["result"]["integer_value"] == 200
    assert found[Metric.PAGE_TITLE]["result"]["text_value"] == "Example Domain"
    assert found[Metric.META_DESCRIPTION]["result"]["text_value"] == "A page used for examples."
    assert found[Metric.CANONICAL_URL]["result"]["url_value"] == "https://example.test/home"
    assert found[Metric.CONTENT_TYPE]["result"]["text_value"] == "text/html; charset=utf-8"
    assert found[Metric.TRANSPORT_IS_HTTPS]["result"]["boolean_value"] is False


def test_every_fact_is_traceable_to_url_time_and_method() -> None:
    envelope = analyse({"/": Route(body=FULL_PAGE, headers=HTML_HEADERS)})
    for measurement in envelope["measurements"]:
        assert measurement["source_url"].startswith("http://127.0.0.1:")
        assert measurement["observed_at"].endswith("Z")
        assert measurement["collector"] == "HOMEPAGE_BASELINE_COLLECTOR"
        assert measurement["collector_version"] == "1.0.0"


def test_known_evidence_references_a_real_measurement() -> None:
    envelope = analyse({"/": Route(body=FULL_PAGE, headers=HTML_HEADERS)})
    ids = {m["measurement_id"] for m in envelope["measurements"]}
    known = [
        e for e in envelope["website_evidence"] if e["assessment"].get("result_state") == "KNOWN"
    ]

    assert known, "canary: the page must have produced known evidence"
    for evidence in known:
        assert evidence["measurement_refs"], "KNOWN evidence must name what it rests on"
        assert set(evidence["measurement_refs"]) <= ids, "evidence references a phantom id"


def test_no_evidence_invents_a_polarity() -> None:
    """These are facts, not judgements. Nothing here decides good or bad about the site."""
    envelope = analyse({"/": Route(body=FULL_PAGE, headers=HTML_HEADERS)})
    for evidence in envelope["website_evidence"]:
        assert "polarity" not in evidence


# --- the run lifecycle is the accepted one ------------------------------------------------


def test_a_successful_analysis_uses_the_accepted_run_lifecycle() -> None:
    envelope = analyse({"/": Route(body=FULL_PAGE, headers=HTML_HEADERS)})
    state = envelope["analysis_run_state"]
    assert state["state"] == "SUCCEEDED"
    assert "finished_at" in state
    assert "failure" not in state
    assert [s["stage_id"] for s in envelope["stage_executions"]] == [
        "PAGE_FETCH",
        "HTML_OBSERVATION",
    ]


# --- a technical failure is never a finding about the website -------------------------------

TECHNICAL_FAILURES = {
    "timeout": (FetchFailureKind.TIMEOUT, "TIMEOUT"),
    "dns": (FetchFailureKind.DNS_FAILURE, "PROVIDER_FAILURE"),
    "connection": (FetchFailureKind.CONNECTION_FAILURE, "PROVIDER_FAILURE"),
    "blocked target": (FetchFailureKind.BLOCKED_TARGET, "PERMISSION_DENIED"),
    "redirect limit": (FetchFailureKind.TOO_MANY_REDIRECTS, "PROVIDER_FAILURE"),
    "invalid redirect": (FetchFailureKind.INVALID_REDIRECT, "PROVIDER_FAILURE"),
    "protocol": (FetchFailureKind.PROTOCOL_ERROR, "PROVIDER_FAILURE"),
}


@pytest.mark.parametrize(
    ("kind", "reason"), TECHNICAL_FAILURES.values(), ids=list(TECHNICAL_FAILURES)
)
def test_a_technical_failure_produces_no_website_finding(kind, reason) -> None:
    envelope = use_case(StubFetcher(PageFetchFailure(kind))).run(
        request_for("https://example.test/")
    )
    assert_envelope_validates(envelope)

    for measurement in envelope["measurements"]:
        assert measurement["assessment"] == {"not_assessed_reason": reason}
        assert "result" not in measurement, "a measurement that never happened carries no value"

    for evidence in envelope["website_evidence"]:
        assert "polarity" not in evidence, "a technical failure cannot speak about the site"
        assert evidence["assessment"] == {"not_assessed_reason": reason}


@pytest.mark.parametrize(
    ("kind", "reason"), TECHNICAL_FAILURES.values(), ids=list(TECHNICAL_FAILURES)
)
def test_a_technical_failure_fails_the_run_rather_than_the_website(kind, reason) -> None:
    envelope = use_case(StubFetcher(PageFetchFailure(kind))).run(
        request_for("https://example.test/")
    )
    state = envelope["analysis_run_state"]
    assert state["state"] == "FAILED"
    assert state["failure"]["code"] in {"PAGE_FETCH_FAILED", "TARGET_NOT_PERMITTED"}


def test_a_blocked_target_is_a_refused_permission_not_a_site_defect() -> None:
    envelope = use_case(StubFetcher(PageFetchFailure(FetchFailureKind.BLOCKED_TARGET))).run(
        request_for("https://example.test/")
    )
    assert envelope["analysis_run_state"]["failure"]["code"] == "TARGET_NOT_PERMITTED"
    reasons = {m["assessment"]["not_assessed_reason"] for m in envelope["measurements"]}
    assert reasons == {"PERMISSION_DENIED"}


def test_a_parser_failure_does_not_fabricate_an_absence() -> None:
    """Our parser breaking says nothing about the page. The transport facts still stand."""

    def broken(body: bytes, declared_charset: str | None = None):
        raise HtmlUnreadable("boom")

    with ControlledHttpServer({"/": Route(body=FULL_PAGE, headers=HTML_HEADERS)}) as server:
        fetcher = SafePageFetcher(policy=loopback_policy())
        envelope = use_case(fetcher, read=broken).run(request_for(server.url("/")))

    assert_envelope_validates(envelope)
    found = measurements_by_metric(envelope)

    assert found[Metric.HTTP_STATUS]["result"]["integer_value"] == 200
    for metric in (Metric.PAGE_TITLE_PRESENT, Metric.PAGE_TITLE, Metric.CANONICAL_URL):
        assert found[metric]["assessment"] == {"not_assessed_reason": "RUNTIME_ERROR"}
        assert "result" not in found[metric]
    for evidence in envelope["website_evidence"]:
        assert "polarity" not in evidence


# --- absence is a fact, and is not a failure ------------------------------------------------


def test_a_missing_element_is_reported_as_a_real_absence() -> None:
    bare = b"<!doctype html><html><head></head><body>nothing declared</body></html>"
    envelope = analyse({"/": Route(body=bare, headers=HTML_HEADERS)})
    assert_envelope_validates(envelope)
    found = measurements_by_metric(envelope)

    for present, value in (
        (Metric.PAGE_TITLE_PRESENT, Metric.PAGE_TITLE),
        (Metric.META_DESCRIPTION_PRESENT, Metric.META_DESCRIPTION),
        (Metric.CANONICAL_PRESENT, Metric.CANONICAL_URL),
    ):
        assert found[present]["result"]["boolean_value"] is False, present
        assert found[present]["assessment"]["result_state"] == "KNOWN"
        # Absent is a fact about the site; there being no value to read is a fact about the
        # measurement. They are different, and neither is a technical failure.
        assert found[value]["assessment"]["result_state"] == "NOT_APPLICABLE"
        assert "result" not in found[value]


def test_an_error_status_stays_a_measured_status() -> None:
    envelope = analyse({"/": Route(status=503, headers=HTML_HEADERS)})
    assert_envelope_validates(envelope)
    found = measurements_by_metric(envelope)

    assert found[Metric.HTTP_STATUS]["result"]["integer_value"] == 503
    assert envelope["analysis_run_state"]["state"] == "SUCCEEDED", (
        "the run executed correctly; the site answering 503 is a measurement, not our failure"
    )
    for evidence in envelope["website_evidence"]:
        assert "polarity" not in evidence


def test_a_non_html_response_makes_the_document_metrics_not_applicable() -> None:
    routes = {"/": Route(body=b"%PDF-1.4", headers={"Content-Type": "application/pdf"})}
    envelope = analyse(routes)
    assert_envelope_validates(envelope)
    found = measurements_by_metric(envelope)

    assert found[Metric.CONTENT_TYPE]["result"]["text_value"] == "application/pdf"
    for metric in (Metric.PAGE_TITLE_PRESENT, Metric.PAGE_TITLE):
        assert found[metric]["assessment"]["result_state"] == "NOT_APPLICABLE"


# --- values the contract cannot carry ---------------------------------------------------------


def test_an_overlong_title_is_never_silently_shortened() -> None:
    """Presence is still known; the value establishes nothing rather than lying by truncation."""
    long_title = "x" * 900
    page = f"<html><head><title>{long_title}</title></head><body>b</body></html>".encode()
    envelope = analyse({"/": Route(body=page, headers=HTML_HEADERS)})
    assert_envelope_validates(envelope)
    found = measurements_by_metric(envelope)

    assert found[Metric.PAGE_TITLE_PRESENT]["result"]["boolean_value"] is True
    assert found[Metric.PAGE_TITLE]["assessment"]["result_state"] == "UNKNOWN"
    assert "result" not in found[Metric.PAGE_TITLE]

    rendered = repr(envelope)
    assert long_title not in rendered
    assert "x" * 500 not in rendered, "a shortened value must not be presented as the original"


def test_a_title_of_only_whitespace_is_an_absence_not_a_value() -> None:
    page = b"<html><head><title>   \n  </title></head><body>b</body></html>"
    found = measurements_by_metric(analyse({"/": Route(body=page, headers=HTML_HEADERS)}))
    assert found[Metric.PAGE_TITLE_PRESENT]["result"]["boolean_value"] is False


def test_a_multiline_title_is_normalised_to_one_line() -> None:
    page = b"<html><head><title>One\n  Two\tThree</title></head><body>b</body></html>"
    found = measurements_by_metric(analyse({"/": Route(body=page, headers=HTML_HEADERS)}))
    assert found[Metric.PAGE_TITLE]["result"]["text_value"] == "One Two Three"


def test_a_relative_canonical_is_resolved_against_the_final_url() -> None:
    page = b'<html><head><link rel="canonical" href="/home"></head><body>b</body></html>'
    with ControlledHttpServer({"/": Route(body=page, headers=HTML_HEADERS)}) as server:
        envelope = use_case(SafePageFetcher(policy=loopback_policy())).run(
            request_for(server.url("/"))
        )
    found = measurements_by_metric(envelope)
    assert found[Metric.CANONICAL_URL]["result"]["url_value"] == server.url("/home")


def test_a_canonical_that_is_not_a_web_url_establishes_nothing() -> None:
    page = (
        b'<html><head><link rel="canonical" href="mailto:a@b.example"></head><body>b</body></html>'
    )
    found = measurements_by_metric(analyse({"/": Route(body=page, headers=HTML_HEADERS)}))
    assert found[Metric.CANONICAL_PRESENT]["result"]["boolean_value"] is True
    assert found[Metric.CANONICAL_URL]["assessment"]["result_state"] == "UNKNOWN"


# --- a truncated read must not manufacture an absence -------------------------------------------


def test_a_truncated_body_reports_unknown_rather_than_absent() -> None:
    """Our own byte limit must never become a defect on the customer's site."""
    filler = b"<p>" + (b"a" * 4000) + b"</p>"
    page = b"<html><head>" + filler + b"<title>Late</title></head><body>b</body></html>"
    envelope = analyse({"/": Route(body=page, headers=HTML_HEADERS)}, max_response_bytes=200)
    assert_envelope_validates(envelope)
    found = measurements_by_metric(envelope)

    assert found[Metric.PAGE_TITLE_PRESENT]["assessment"]["result_state"] == "UNKNOWN"
    assert "result" not in found[Metric.PAGE_TITLE_PRESENT]
    assert found[Metric.HTTP_STATUS]["result"]["integer_value"] == 200


# --- determinism ---------------------------------------------------------------------------------


def test_the_same_frozen_input_produces_the_same_documents() -> None:
    stub = StubFetcher(PageFetchFailure(FetchFailureKind.TIMEOUT))
    first = use_case(stub).run(request_for("https://example.test/"))
    second = use_case(stub).run(request_for("https://example.test/"))
    assert first == second


def test_a_repeated_analysis_of_one_frozen_response_is_identical() -> None:
    with ControlledHttpServer({"/": Route(body=FULL_PAGE, headers=HTML_HEADERS)}) as server:
        url = server.url("/")
        runs = [
            use_case(SafePageFetcher(policy=loopback_policy())).run(request_for(url))
            for _ in range(3)
        ]
    assert runs[0] == runs[1] == runs[2]


# --- no raw payload reaches a normalised record ------------------------------------------


def test_no_raw_response_body_appears_in_any_normalised_document() -> None:
    marker = b"UNIQUE-BODY-MARKER-9f3a"
    page = b"<html><head><title>T</title></head><body>" + marker + b"</body></html>"
    envelope = analyse({"/": Route(body=page, headers=HTML_HEADERS)})

    for member in ("measurements", "website_evidence", "analysis_run_state", "stage_executions"):
        assert marker.decode() not in repr(envelope[member]), member
