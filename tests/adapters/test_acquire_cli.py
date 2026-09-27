"""The acquisition command line and its production wiring.

Three things are proved here and nowhere else. The command line has **no default page count**:
``--max-selected-pages N`` is required, validated, and handed on as the manifest's declared
selection budget. The production composition puts the shipped strict ``SafePageFetcher`` in front
of **every selected page**, so the orchestration cannot become a way around the safety boundary —
proved without network by giving the shipped policy fake DNS answers. And the artifacts the
command writes are validated again *after* they are read back from disk.

``SafePageFetcher``'s own safety cases are not repeated (D-20-O); ``test_page_fetcher.py`` stays
their regression evidence. The loopback integration below proves only that the orchestration
carries the fetcher's real outcomes through to truthful records.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import pytest

from pxapi.adapters.composition import build_site_acquisition
from pxapi.adapters.inbound import acquire_cli
from pxapi.adapters.web.html_observations import read_html
from pxapi.adapters.web.page_fetcher import SafePageFetcher
from pxapi.adapters.web.target_policy import PublicTargetPolicy
from pxapi.application.acquire_selected_pages import AcquireSelectedPages
from pxapi.application.discover_site import DiscoverSite
from pxapi.application.observe_static_page import StaticPageObserver
from pxapi.config.fetch_limits import DEFAULT_FETCH_LIMITS, FetchLimits
from pxapi.domain.sampling_policy import SelectionBudgets
from pxapi.domain.site_discovery import (
    DiscoveryObservation,
    DiscoveryReport,
    SourceAttempt,
    SourceOutcome,
)
from tests.adapters.http_test_server import ControlledHttpServer, Route, loopback_policy
from tests.application.test_acquire_selected_pages import (
    ORIGIN,
    SELECTED,
    FakeFetcher,
    build,
    clock,
    counting_ids,
    report,
)
from tests.application.test_discover_site import FakeDiscovery
from tests.contracts.support import CONTRACTS

HTML_HEADERS = {"Content-Type": "text/html; charset=utf-8"}


def stub(monkeypatch: pytest.MonkeyPatch, tamper: Any = None) -> list[SelectionBudgets]:
    """Replace the production wiring with fakes, recording the budgets the CLI declared."""
    declared: list[SelectionBudgets] = []

    def fake_build(budgets: SelectionBudgets, registry: Any = None) -> Any:
        declared.append(budgets)
        use = build(FakeFetcher(), budgets.max_selected_pages)
        if tamper is None:
            return use

        class Tampered:
            def run(self, request: dict[str, Any]) -> dict[str, Any]:
                envelope = use.run(request)
                tamper(envelope)
                return envelope

        return Tampered()

    monkeypatch.setattr(acquire_cli, "build_site_acquisition", fake_build)
    return declared


# --- the budget is explicit ---------------------------------------------------------------------


def test_the_page_budget_is_required_and_has_no_default(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exited:
        acquire_cli.main([ORIGIN])
    assert exited.value.code == 2
    assert "--max-selected-pages" in capsys.readouterr().err


@pytest.mark.parametrize("value", ["0", "-1", "abc", "1.5", "", "٣", "+3"])
def test_a_budget_that_is_not_a_whole_number_of_at_least_one_is_refused(value: str) -> None:
    with pytest.raises(SystemExit) as exited:
        acquire_cli.main([ORIGIN, f"--max-selected-pages={value}"])
    assert exited.value.code == 2


def test_a_valid_budget_is_read_as_that_number() -> None:
    assert acquire_cli.page_budget("3") == 3
    assert acquire_cli.page_budget("1") == 1


def test_the_budget_becomes_the_manifest_s_declared_selection_budget(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    declared = stub(monkeypatch)
    assert acquire_cli.main([ORIGIN, "--max-selected-pages", "3"]) == 0
    assert declared == [SelectionBudgets(max_selected_pages=3)]

    envelope = json.loads(capsys.readouterr().out)
    manifest = envelope["sampling_manifest"]
    assert manifest["budgets"] == {"max_selected_pages": 3}
    assert manifest["selection_complete"] is False
    assert manifest["incompleteness"] == {"cause": "SELECTION_BUDGET_EXHAUSTED"}
    # One record per selection, and exactly the selection: no second truncation.
    assert [r["url_key"] for r in envelope["page_acquisitions"]] == SELECTED[:3]


# --- canonical output ------------------------------------------------------------------------------


def test_a_document_that_fails_its_own_contract_is_withheld(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub(monkeypatch, tamper=lambda e: e["measurements"][0].update(schema_version="9.9.9"))
    assert acquire_cli.main([ORIGIN, "--max-selected-pages", "2"]) == 3
    output = json.loads(capsys.readouterr().out)
    assert output["code"] == "CANONICAL_OUTPUT_INVALID"
    assert "9.9.9" not in json.dumps(output)
    assert CONTRACTS.validate("problem", output) == ()


def test_the_output_check_covers_every_page_document_contract() -> None:
    envelope = {"page_acquisitions": [{}], "measurements": [{}], "website_evidence": [{}]}
    assert acquire_cli.invalid_documents(CONTRACTS, envelope) == [
        "page-acquisition-record",
        "measurement-record",
        "website-evidence",
    ]


def test_the_artifacts_are_written_read_back_and_summarised_per_page(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    stub(monkeypatch)
    out = tmp_path / "run"
    assert acquire_cli.main([ORIGIN, "--max-selected-pages", "3", "--output-dir", str(out)]) == 0
    capsys.readouterr()

    for _contract, file_name in acquire_cli.PRODUCED_DOCUMENTS.values():
        assert (out / file_name).is_file(), file_name
    assert acquire_cli.read_back_problems(out, CONTRACTS) == []

    receipt = json.loads((out / acquire_cli.RECEIPT_FILE).read_text(encoding="utf-8"))
    assert receipt["run_state"] == "SUCCEEDED"
    assert receipt["sampling_manifest"]["selection_complete"] is False
    assert receipt["sampling_manifest"]["incompleteness"] == {
        "cause": "SELECTION_BUDGET_EXHAUSTED"
    }
    assert [row["selection_rank"] for row in receipt["pages"]] == [1, 2, 3]
    assert [row["url_key"] for row in receipt["pages"]] == SELECTED[:3]
    measurements = json.loads((out / "measurement-records.json").read_text(encoding="utf-8"))
    evidence = json.loads((out / "website-evidence.json").read_text(encoding="utf-8"))
    evidence_refs = {e["evidence_id"]: e["measurement_refs"] for e in evidence}
    for row in receipt["pages"]:
        assert row["acquisition_outcome"] == "RESPONSE_RECEIVED"
        assert row["http_status"] == 200
        assert len(row["evidence_refs"]) == len(row["measurement_refs"]) > 0
        for evidence_id in row["evidence_refs"]:
            assert set(evidence_refs[evidence_id]) <= set(row["measurement_refs"])
    assert sum(len(row["measurement_refs"]) for row in receipt["pages"]) == len(measurements)
    assert set(receipt["document_digests"]) == {
        "page_acquisitions",
        "measurements",
        "website_evidence",
    }


def test_the_read_back_sees_an_artifact_altered_on_disk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    stub(monkeypatch)
    out = tmp_path / "run"
    assert acquire_cli.main([ORIGIN, "--max-selected-pages", "3", "--output-dir", str(out)]) == 0
    capsys.readouterr()

    path = out / "page-acquisition-records.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(list(reversed(records))), encoding="utf-8")
    problems = acquire_cli.read_back_problems(out, CONTRACTS)
    assert any("one_record_per_selection" in problem for problem in problems), problems


def test_a_credential_bearing_target_is_refused_without_being_echoed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub(monkeypatch)
    target = "https://user:secret@example.com/"
    assert acquire_cli.main([target, "--max-selected-pages", "3"]) == 2
    captured = capsys.readouterr()
    assert "secret" not in captured.out and "secret" not in captured.err


def test_an_invalid_target_is_refused_by_the_request_contract(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert acquire_cli.main(["not a url", "--max-selected-pages", "3"]) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "CONTRACT_VALIDATION_FAILED"


# --- the production wiring ----------------------------------------------------------------------


def test_the_production_acquisition_requires_a_declared_budget() -> None:
    parameter = inspect.signature(build_site_acquisition).parameters["budgets"]
    assert parameter.default is inspect.Parameter.empty


def test_the_production_acquisition_is_strict_and_uses_the_declared_budget_only() -> None:
    budgets = SelectionBudgets(max_selected_pages=3)
    use = build_site_acquisition(budgets)

    assert isinstance(use, AcquireSelectedPages)
    assert isinstance(use.discover, DiscoverSite)
    assert use.discover.budgets is budgets
    assert type(use.fetcher) is SafePageFetcher
    assert type(use.fetcher.policy) is PublicTargetPolicy
    assert use.fetcher.limits == DEFAULT_FETCH_LIMITS
    assert use.observer.max_text_length == CONTRACTS.max_single_line_text()


def test_the_production_wiring_refuses_a_loopback_target_before_any_connection() -> None:
    use = build_site_acquisition(SelectionBudgets(max_selected_pages=3))
    envelope = use.run({"run_id": "run-1", "target_url": "http://127.0.0.1:9/"})
    assert envelope["analysis_run_state"]["failure"] == {"code": "TARGET_NOT_PERMITTED"}
    assert not {"sampling_manifest", "page_acquisitions"} & set(envelope)


def _with_dns(answer: Any) -> AcquireSelectedPages:
    """The production acquisition, with a frozen selection and the shipped policy fed ``answer``.

    Only the DNS answer is replaced; the policy class, its address rule, the fetcher and its
    limits are the production objects. No socket can be opened, because every answer below is
    refused before one would be.
    """
    use = build_site_acquisition(SelectionBudgets(max_selected_pages=4))
    use.discover = DiscoverSite(
        FakeDiscovery(report()), clock, counting_ids(), SelectionBudgets(max_selected_pages=4)
    )
    assert isinstance(use.fetcher, SafePageFetcher)
    use.fetcher.policy.resolve = answer
    return use


def _refusing_resolver(host: str, port: int) -> list[str]:
    raise OSError("name does not resolve")


@pytest.mark.parametrize(
    ("answer", "outcome"),
    [
        (lambda host, port: ["10.0.0.7"], "BLOCKED_TARGET"),
        (lambda host, port: ["169.254.169.254"], "BLOCKED_TARGET"),
        # Partial resolution is fatal: one public answer beside a loopback one is a rebinding
        # shape, and the page is refused before any connection.
        (lambda host, port: ["93.184.216.34", "127.0.0.1"], "BLOCKED_TARGET"),
        (_refusing_resolver, "DNS_FAILURE"),
    ],
    ids=["private", "link-local", "rebinding", "dns-failure"],
)
def test_every_selected_page_passes_through_the_shipped_safety_boundary(
    answer: Any, outcome: str
) -> None:
    envelope = _with_dns(answer).run(
        {
            "schema_version": "1.0.0",
            "run_id": "run-1",
            "request_id": "req-1",
            "requested_at": "2026-09-27T12:00:00Z",
            "target_url": ORIGIN,
            "scan_mode": "PUBLIC_NON_INVASIVE",
        }
    )
    assert envelope["analysis_run_state"]["state"] == "SUCCEEDED"
    records = envelope["page_acquisitions"]
    assert [r["url_key"] for r in records] == SELECTED
    assert {r["acquisition_outcome"] for r in records} == {outcome}
    assert acquire_cli.invalid_documents(CONTRACTS, envelope) == []


# --- the real fetcher's outcomes, carried through to records -----------------------------------


def test_real_fetch_outcomes_over_loopback_become_truthful_page_records() -> None:
    big = b"<html><head><title>x</title></head><body>" + b"a" * 5_000 + b"</body></html>"
    routes = {
        "/": Route(body=b"<html><head><title>Start</title></head></html>", headers=HTML_HEADERS),
        "/a": Route(status=301, headers={"Location": "/a"}),
        "/b": Route(status=302),
        "/c": Route(body=big, headers=HTML_HEADERS),
        "/d": Route(status=404, body=b"<title>Nicht gefunden</title>", headers=HTML_HEADERS),
        "/e": Route(body=b"xx", headers={**HTML_HEADERS, "Content-Encoding": "br"}),
    }
    with ControlledHttpServer(routes) as server:
        origin = server.url("/")
        pages = [origin, *(server.url(path) for path in ("/a", "/b", "/c", "/d", "/e"))]
        seen = DiscoveryReport(
            target_origin=origin,
            observations=(
                DiscoveryObservation(origin, "CANONICAL_SEED"),
                *(DiscoveryObservation(page, "SITEMAP") for page in pages[1:]),
            ),
            attempts=(
                SourceAttempt("CANONICAL_SEED", SourceOutcome.USED),
                SourceAttempt("SITEMAP", SourceOutcome.USED),
            ),
        )
        ids = counting_ids()
        budgets = SelectionBudgets(max_selected_pages=6)
        limits = FetchLimits(max_response_bytes=1_000)
        use = AcquireSelectedPages(
            DiscoverSite(FakeDiscovery(seen), clock, ids, budgets),
            SafePageFetcher(policy=loopback_policy(), limits=limits),
            StaticPageObserver(read_html, ids, CONTRACTS.max_single_line_text()),
            clock,
            ids,
        )
        envelope = use.run({"run_id": "run-1", "target_url": origin})

    records = {r["url_key"]: r for r in envelope["page_acquisitions"]}
    assert list(records) == pages
    assert records[pages[0]]["acquisition_outcome"] == "RESPONSE_RECEIVED"
    assert records[pages[1]]["acquisition_outcome"] == "TOO_MANY_REDIRECTS"
    assert records[pages[2]]["acquisition_outcome"] == "INVALID_REDIRECT"
    assert records[pages[3]]["body_truncated"] is True
    assert records[pages[4]]["http_status"] == 404
    assert records[pages[5]]["body_decoded"] is False
    assert "body_digest" not in records[pages[5]]
    assert "Nicht gefunden" not in json.dumps(envelope)
    assert envelope["analysis_run_state"]["state"] == "SUCCEEDED"
    for member in ("page_acquisitions", "measurements", "website_evidence"):
        contract, _file = acquire_cli.PRODUCED_DOCUMENTS[member]
        assert all(CONTRACTS.validate(contract, d) == () for d in envelope[member]), member
