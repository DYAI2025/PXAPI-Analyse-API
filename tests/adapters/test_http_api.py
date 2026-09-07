"""The HTTP boundary: routing, status codes, and nothing else.

The endpoint's job is to hand a body to the contract registry and a validated document to the
use case. These tests hold it to that: every rejection is a `problem` document that itself
validates, and no contract shape is restated as a framework model anywhere in the route.
"""

from __future__ import annotations

import inspect
import json

import pytest
from fastapi.testclient import TestClient

from pxapi.adapters.contracts.registry import ContractRegistry
from pxapi.adapters.inbound import http_api
from pxapi.adapters.inbound.http_api import create_app
from pxapi.adapters.web.page_fetcher import SafePageFetcher
from pxapi.application.analyze_homepage import AnalyzeHomepage
from pxapi.config.contract_root import contract_root
from tests.adapters.http_test_server import ControlledHttpServer, Route, loopback_policy
from tests.application.test_analyze_homepage import (
    FULL_PAGE,
    HTML_HEADERS,
    MEMBER_CONTRACT,
    counting_ids,
    frozen_clock,
    request_for,
)

CONTRACTS = ContractRegistry(contract_root())
ENDPOINT = "/v1/analysis-runs"


def client_for(server: ControlledHttpServer | None = None) -> TestClient:
    """A client whose use case reaches the controlled server, when one is given."""
    if server is None:
        return TestClient(create_app(registry=CONTRACTS), raise_server_exceptions=False)

    from pxapi.adapters.web.html_observations import read_html

    analyzer = AnalyzeHomepage(
        fetcher=SafePageFetcher(policy=loopback_policy()),
        read_html=read_html,
        clock=frozen_clock(),
        new_id=counting_ids(),
        max_text_length=CONTRACTS.max_single_line_text(),
    )
    return TestClient(create_app(registry=CONTRACTS, analyzer=analyzer))


# --- the happy path --------------------------------------------------------------------


def test_a_valid_request_returns_a_fully_valid_envelope() -> None:
    with ControlledHttpServer({"/": Route(body=FULL_PAGE, headers=HTML_HEADERS)}) as server:
        response = client_for(server).post(ENDPOINT, json=request_for(server.url("/")))

    assert response.status_code == 200
    envelope = response.json()
    for member, contract in MEMBER_CONTRACT.items():
        value = envelope[member]
        documents = value if isinstance(value, list) else [value]
        for document in documents:
            assert CONTRACTS.validate(contract, document) == (), member


def test_the_response_carries_the_facts_an_operator_reads_back() -> None:
    with ControlledHttpServer({"/": Route(body=FULL_PAGE, headers=HTML_HEADERS)}) as server:
        envelope = client_for(server).post(ENDPOINT, json=request_for(server.url("/"))).json()

    assert envelope["analysis_run_state"]["run_id"] == "run-0001"
    assert envelope["analysis_run_request"]["scan_mode"] == "PUBLIC_NON_INVASIVE"
    assert envelope["analysis_run_state"]["state"] == "SUCCEEDED"
    metrics = {m["metric_id"] for m in envelope["measurements"]}
    assert {"HTTP_STATUS", "PAGE_TITLE", "META_DESCRIPTION", "CANONICAL_URL"} <= metrics


# --- rejections, each a valid problem document -------------------------------------------


def assert_is_problem(response, code: str, status: int) -> dict:
    assert response.status_code == status, response.text
    document = response.json()
    assert CONTRACTS.validate("problem", document) == (), document
    assert document["code"] == code
    return document


def test_a_body_that_is_not_json_is_refused() -> None:
    response = client_for().post(
        ENDPOINT, content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert_is_problem(response, "MALFORMED_REQUEST_BODY", 400)


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_a_body_using_a_non_json_constant_is_refused(literal: str) -> None:
    """`NaN` is not JSON, and a numeric bound compares False against it rather than failing."""
    body = '{"schema_version": ' + literal + "}"
    response = client_for().post(
        ENDPOINT, content=body.encode(), headers={"Content-Type": "application/json"}
    )
    assert_is_problem(response, "MALFORMED_REQUEST_BODY", 400)


def test_a_body_that_is_not_an_object_is_refused_by_the_contract() -> None:
    response = client_for().post(ENDPOINT, json=[1, 2, 3])
    assert_is_problem(response, "CONTRACT_VALIDATION_FAILED", 422)


@pytest.mark.parametrize(
    "missing", ["run_id", "request_id", "requested_at", "target_url", "scan_mode"]
)
def test_a_request_missing_a_required_member_is_refused(missing: str) -> None:
    document = request_for("https://example.test/")
    del document[missing]
    problem = assert_is_problem(
        client_for().post(ENDPOINT, json=document), "CONTRACT_VALIDATION_FAILED", 422
    )
    assert {"pointer": "", "keyword": "required"} in problem["errors"]


@pytest.mark.parametrize(
    "url", ["not-a-url", "ftp://example.com/", "javascript:alert(1)", "/relative"]
)
def test_a_target_url_that_is_not_an_http_url_is_refused_by_the_contract(url: str) -> None:
    problem = assert_is_problem(
        client_for().post(ENDPOINT, json=request_for(url)), "CONTRACT_VALIDATION_FAILED", 422
    )
    assert {"pointer": "/target_url", "keyword": "pattern"} in problem["errors"]


def test_an_unsupported_schema_version_is_reported_as_such() -> None:
    document = request_for("https://example.test/") | {"schema_version": "2.0.0"}
    assert_is_problem(client_for().post(ENDPOINT, json=document), "SCHEMA_VERSION_UNSUPPORTED", 422)


def test_an_unimplemented_scan_mode_is_refused_rather_than_downgraded() -> None:
    """The mode records what the run was authorised under; running it as another mode lies."""
    document = request_for("https://example.test/") | {"scan_mode": "OWNER_VERIFIED_CONTROLLED"}
    problem = assert_is_problem(
        client_for().post(ENDPOINT, json=document), "SCAN_MODE_NOT_SUPPORTED", 422
    )
    assert problem["run_id"] == "run-0001"


def test_a_rejection_never_echoes_the_submitted_document() -> None:
    """A refused request is described structurally: pointer and keyword, never its content."""
    document = request_for("https://example.test/<script>alert(1)</script>") | {
        "schema_version": "2.0.0",
        "requester_ref": "tok_SECRET_VALUE",
    }
    response = client_for().post(ENDPOINT, json=document)
    rendered = json.dumps(assert_is_problem(response, "SCHEMA_VERSION_UNSUPPORTED", 422))

    assert "tok_SECRET_VALUE" not in rendered
    assert "<script>" not in rendered
    assert "2.0.0" not in rendered


def test_an_accepted_request_is_echoed_back_for_traceability() -> None:
    """The accepted request is the caller's own document, and the envelope's provenance.

    It is echoed because the response must state what was asked for and under which mode; it
    is the one place a submitted value legitimately reappears, and only after it validated.
    """
    with ControlledHttpServer({"/": Route(body=FULL_PAGE, headers=HTML_HEADERS)}) as server:
        document = request_for(server.url("/")) | {"requester_ref": "opaque-ref-1"}
        envelope = client_for(server).post(ENDPOINT, json=document).json()

    assert envelope["analysis_run_request"] == document


# --- a blocked target is a run outcome, not a crash ----------------------------------------


def test_a_loopback_target_is_refused_by_the_real_policy() -> None:
    """The default wiring uses the strict policy, so this never reaches the network."""
    response = client_for().post(ENDPOINT, json=request_for("http://127.0.0.1:9/"))

    assert response.status_code == 200
    envelope = response.json()
    assert envelope["analysis_run_state"]["state"] == "FAILED"
    assert envelope["analysis_run_state"]["failure"]["code"] == "TARGET_NOT_PERMITTED"
    reasons = {m["assessment"]["not_assessed_reason"] for m in envelope["measurements"]}
    assert reasons == {"PERMISSION_DENIED"}
    for evidence in envelope["website_evidence"]:
        assert "polarity" not in evidence


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://[::1]/",
    ],
)
def test_a_private_or_metadata_target_never_becomes_a_website_finding(url: str) -> None:
    envelope = client_for().post(ENDPOINT, json=request_for(url)).json()
    assert envelope["analysis_run_state"]["failure"]["code"] == "TARGET_NOT_PERMITTED"
    for measurement in envelope["measurements"]:
        assert "result" not in measurement
    for evidence in envelope["website_evidence"]:
        assert "polarity" not in evidence


# --- the framework holds no contract shape --------------------------------------------------


def test_the_route_binds_no_model_for_the_request_body() -> None:
    """A framework model restating a contract would be a second authority. There is none."""
    route = next(
        r for r in create_app(registry=CONTRACTS).routes if getattr(r, "path", "") == ENDPOINT
    )
    parameters = inspect.signature(route.endpoint).parameters
    # `from __future__ import annotations` leaves these as strings, which is what we compare.
    annotations = {str(p.annotation) for p in parameters.values()}
    assert annotations == {"Request"}, annotations


def test_the_module_defines_no_pydantic_model() -> None:
    import pydantic

    models = [
        name
        for name, value in vars(http_api).items()
        if isinstance(value, type) and issubclass(value, pydantic.BaseModel)
    ]
    assert models == [], f"the transport defines contract model(s) {models}"


def test_the_openapi_document_declares_no_request_schema_for_the_endpoint() -> None:
    spec = create_app(registry=CONTRACTS).openapi()
    operation = spec["paths"][ENDPOINT]["post"]
    assert "requestBody" not in operation


# --- the new canonical member crosses the boundary, and is gated there ----------------------


def test_the_endpoint_returns_diagnostic_findings_bound_to_the_evidence_it_served() -> None:
    """The findings are part of the canonical response, and their chain survives the transport."""
    with ControlledHttpServer({"/": Route(status=503, body=FULL_PAGE, headers=HTML_HEADERS)}) as s:
        envelope = client_for(s).post(ENDPOINT, json=request_for(s.url("/"))).json()

    findings = envelope["diagnostic_findings"]
    assert findings, "a 503 over plain HTTP must produce findings"
    evidence_ids = {e["evidence_id"] for e in envelope["website_evidence"]}
    for finding in findings:
        assert CONTRACTS.validate("diagnostic-finding", finding) == (), finding
        assert set(finding["evidence_refs"]) <= evidence_ids, (
            "a finding references phantom evidence"
        )


def test_a_refused_target_returns_no_finding_over_the_wire() -> None:
    """A permission our process was refused is not something the website did."""
    envelope = client_for().post(ENDPOINT, json=request_for("http://127.0.0.1:9/")).json()
    assert envelope["analysis_run_state"]["failure"]["code"] == "TARGET_NOT_PERMITTED"
    assert envelope["diagnostic_findings"] == []


def test_a_finding_that_fails_its_own_contract_is_withheld_rather_than_served() -> None:
    """The outbound gate covers the new member too, not merely the ones PXK-67 shipped.

    A document this service produced that does not satisfy the contract it claims is a defect
    in this service. It is reported as one and never returned, so a malformed finding cannot
    reach a consumer as though it were an analysis result.
    """

    class BrokenFindings(AnalyzeHomepage):
        def _findings(self, run_id, measurements, evidence):  # type: ignore[override]
            # Evidence is the Fact Authority; a finding resting on nothing is exactly the
            # shape the contract refuses.
            return [
                dict(document, evidence_refs=[])
                for document in super()._findings(run_id, measurements, evidence)
            ] or [{"schema_version": "1.0.0"}]

    from pxapi.adapters.web.html_observations import read_html

    with ControlledHttpServer({"/": Route(body=FULL_PAGE, headers=HTML_HEADERS)}) as server:
        analyzer = BrokenFindings(
            fetcher=SafePageFetcher(policy=loopback_policy()),
            read_html=read_html,
            clock=frozen_clock(),
            new_id=counting_ids(),
            max_text_length=CONTRACTS.max_single_line_text(),
        )
        client = TestClient(create_app(registry=CONTRACTS, analyzer=analyzer))
        response = client.post(ENDPOINT, json=request_for(server.url("/")))

    document = assert_is_problem(response, "CANONICAL_OUTPUT_INVALID", 500)
    assert "diagnostic_findings" not in json.dumps(document)
