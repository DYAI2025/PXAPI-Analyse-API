"""The discovery command line: it validates what it produced before it prints anything."""

from __future__ import annotations

import json
from typing import Any

import pytest

from pxapi.adapters.inbound import discover_cli
from pxapi.application.discover_site import DiscoverSite
from pxapi.domain.sampling_policy import SelectionBudgets
from pxapi.domain.site_discovery import (
    DiscoveryObservation,
    DiscoveryReport,
    SourceAttempt,
    SourceOutcome,
)
from tests.application.test_discover_site import FakeDiscovery
from tests.contracts.support import CONTRACTS

ORIGIN = "https://example.com/"
REPORT = DiscoveryReport(
    ORIGIN,
    (DiscoveryObservation(ORIGIN, "CANONICAL_SEED"),),
    (SourceAttempt("CANONICAL_SEED", SourceOutcome.USED),),
)


def stub(monkeypatch: pytest.MonkeyPatch, tamper: Any = None) -> None:
    def build() -> Any:
        use = DiscoverSite(
            FakeDiscovery(REPORT), discover_cli_clock, lambda: "id-1", SelectionBudgets(25)
        )
        if tamper is None:
            return use

        class Tampered:
            def run(self, request: dict[str, Any]) -> dict[str, Any]:
                envelope = use.run(request)
                tamper(envelope)
                return envelope

        return Tampered()

    monkeypatch.setattr(discover_cli, "build_site_discovery", build)


def discover_cli_clock() -> Any:
    from datetime import UTC, datetime

    return datetime(2026, 9, 11, 12, 0, 0, tzinfo=UTC)


def test_a_valid_run_prints_every_document_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub(monkeypatch)
    assert discover_cli.main([ORIGIN]) == 0
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["site_inventory"]["target_origin"] == ORIGIN
    assert envelope["sampling_manifest"]["mode"] == "CENSUS"


def test_a_document_that_fails_its_own_contract_is_withheld(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub(monkeypatch, tamper=lambda e: e["site_inventory"].update(schema_version="9.9.9"))
    assert discover_cli.main([ORIGIN]) == 3
    output = json.loads(capsys.readouterr().out)
    assert output["code"] == "CANONICAL_OUTPUT_INVALID"
    assert "site_inventory" not in output and "9.9.9" not in json.dumps(output)
    assert CONTRACTS.validate("problem", output) == ()


def test_an_invalid_target_is_refused_by_the_request_contract(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert discover_cli.main(["not a url"]) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "CONTRACT_VALIDATION_FAILED"


def test_the_output_check_names_every_contract_a_document_fails() -> None:
    envelope = {
        "analysis_run_state": {},
        "stage_executions": [{}, {}],
        "site_inventory": {},
        "sampling_manifest": {},
    }
    assert discover_cli.invalid_documents(CONTRACTS, envelope) == [
        "analysis-run-state",
        "stage-execution-record",
        "stage-execution-record",
        "site-inventory",
        "sampling-manifest",
    ]


def test_a_credential_bearing_target_is_refused_without_being_echoed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub(monkeypatch)
    assert discover_cli.main(["https://user:secret@example.com/"]) == 2
    captured = capsys.readouterr()
    assert "secret" not in captured.out and "secret" not in captured.err


def test_the_production_wiring_is_strict_and_refuses_loopback_before_any_connection() -> None:
    """``build_site_discovery`` is what the CLI and the smoke run. Driven without any network:
    an IP-literal loopback target is refused by the shipped policy before a lookup or a socket."""
    from pxapi.adapters.composition import build_site_discovery
    from pxapi.adapters.web.site_discovery import HttpSiteDiscovery
    from pxapi.config.discovery_limits import DEFAULT_DISCOVERY_LIMITS

    use = build_site_discovery()
    assert isinstance(use.discovery, HttpSiteDiscovery)
    assert use.discovery.limits == DEFAULT_DISCOVERY_LIMITS
    assert use.budgets.max_selected_pages == DEFAULT_DISCOVERY_LIMITS.max_selected_pages
    envelope = use.run({"run_id": "run-1", "target_url": "http://127.0.0.1:9/"})
    assert envelope["analysis_run_state"]["failure"] == {"code": "TARGET_NOT_PERMITTED"}
    assert "site_inventory" not in envelope
