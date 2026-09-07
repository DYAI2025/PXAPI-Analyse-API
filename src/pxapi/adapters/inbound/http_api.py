"""The synchronous HTTP boundary: one endpoint, and no analysis logic whatsoever.

The framework owns routing, the request body and status codes. It owns nothing else. In
particular **no contract shape is expressed as a Python model here**: the body is read as raw
JSON and handed to the contract registry, which validates it against the same schema the tests
use. A framework model restating a contract would be a second authority, free to drift from the
schema it claims to mirror, and this module exists partly to make sure that never happens.

What leaves is validated too. A document this service produced that does not satisfy its own
contract is a defect in this service, so it is withheld and reported as one — never returned
unvalidated and never described as a finding about the analysed site.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from pxapi.adapters.composition import SUPPORTED_SCAN_MODE, build_analyzer, default_registry
from pxapi.adapters.contracts.registry import ContractRegistry, loads_json
from pxapi.application.analyze_homepage import AnalyzeHomepage

#: The request contract this endpoint accepts.
REQUEST_CONTRACT = "analysis-run-request"

#: Which contract each envelope member must satisfy on the way out.
OUTPUT_CONTRACTS: dict[str, str] = {
    "analysis_run_request": REQUEST_CONTRACT,
    "analysis_run_state": "analysis-run-state",
    "stage_executions": "stage-execution-record",
    "measurements": "measurement-record",
    "website_evidence": "website-evidence",
    "diagnostic_findings": "diagnostic-finding",
}

#: Problem code to HTTP status. The `problem` contract is transport-neutral by design, so the
#: mapping onto HTTP lives here, in the adapter that owns the transport, and nowhere else.
STATUS_FOR_CODE: dict[str, int] = {
    "MALFORMED_REQUEST_BODY": 400,
    "CONTRACT_VALIDATION_FAILED": 422,
    "SCHEMA_VERSION_UNSUPPORTED": 422,
    "SCAN_MODE_NOT_SUPPORTED": 422,
    "CANONICAL_OUTPUT_INVALID": 500,
}


def _problem_response(document: dict[str, Any]) -> JSONResponse:
    return JSONResponse(status_code=STATUS_FOR_CODE[document["code"]], content=document)


def create_app(
    registry: ContractRegistry | None = None,
    analyzer: AnalyzeHomepage | None = None,
) -> FastAPI:
    """Build the application. The arguments exist for tests; the defaults are the real thing."""
    registry = registry or default_registry()
    analyzer = analyzer or build_analyzer(registry)

    app = FastAPI(
        title="PXAPI Analysis",
        version="0.1.0",
        description=(
            "Walking skeleton: one public homepage URL in, canonical analysis documents out. "
            "No authentication, no rate limiting, no persistence."
        ),
    )

    @app.post("/v1/analysis-runs")
    async def create_analysis_run(request: Request) -> JSONResponse:
        raw = await request.body()

        try:
            document = loads_json(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            # The decoder's message quotes the submitted bytes, which are untrusted; only the
            # category is reported.
            return _problem_response(
                registry.problem(
                    "MALFORMED_REQUEST_BODY",
                    "Malformed request body",
                    "The request body could not be read as JSON.",
                )
            )

        found = registry.validate(REQUEST_CONTRACT, document)
        if found:
            return _problem_response(registry.to_problem(REQUEST_CONTRACT, found))

        if document.get("scan_mode") != SUPPORTED_SCAN_MODE:
            # A valid mode this slice has not implemented. Refusing is the honest answer;
            # running it as if it were the public mode would misreport what was authorised.
            return _problem_response(
                registry.problem(
                    "SCAN_MODE_NOT_SUPPORTED",
                    "Scan mode not supported",
                    f"This deployment implements the scan mode {SUPPORTED_SCAN_MODE} only.",
                    run_id=document.get("run_id"),
                )
            )

        envelope = analyzer.run(document)

        invalid = _output_violations(registry, envelope)
        if invalid:
            return _problem_response(
                registry.problem(
                    "CANONICAL_OUTPUT_INVALID",
                    "Canonical output invalid",
                    f"This service produced {invalid} document(s) that fail their own contract.",
                    run_id=document.get("run_id"),
                )
            )

        return JSONResponse(status_code=200, content=envelope)

    return app


def _output_violations(registry: ContractRegistry, envelope: dict[str, Any]) -> int:
    """How many produced documents fail the contract they claim."""
    invalid = 0
    for member, contract in OUTPUT_CONTRACTS.items():
        value = envelope[member]
        documents = value if isinstance(value, list) else [value]
        invalid += sum(1 for document in documents if registry.validate(contract, document))
    return invalid


#: The ASGI application, for `uvicorn pxapi.adapters.inbound.http_api:app`.
app = create_app()
