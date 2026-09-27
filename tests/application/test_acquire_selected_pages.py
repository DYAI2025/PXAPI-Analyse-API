"""The multi-page acquisition runtime, driven through fake ports: admission, completeness,
linkage, neutral containment, determinism, and our own defects staying visible.

Discovery and planning are the real ``DiscoverSite`` over a frozen report, the observer is the
real ``StaticPageObserver`` with the real HTML reader, and every document is validated through the
same registry check the command line applies. Only the fetch port is faked, so each per-page
outcome can be stated exactly; that the real ``SafePageFetcher`` stays in front of every page is
proved separately in ``tests/adapters/test_acquire_cli.py``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from pxapi.adapters.inbound.acquire_cli import invalid_documents
from pxapi.adapters.web.html_observations import read_html
from pxapi.application.acquire_selected_pages import (
    ACQUISITION_WITHHELD_CODE,
    PAGE_ACQUISITION_STAGE,
    SELECTION_NOT_ADMISSIBLE_CODE,
    AcquireSelectedPages,
)
from pxapi.application.discover_site import DiscoverSite
from pxapi.application.observe_static_page import (
    NON_SUCCESS_NOT_ASSESSED,
    NOT_ASSESSED_FOR,
    PAGE_METRICS,
    STATIC_PAGE_COLLECTOR,
    StaticPageObserver,
)
from pxapi.domain.observations import Metric
from pxapi.domain.page_acquisition import (
    ACQUISITION_METHOD,
    ACQUISITION_METHOD_VERSION,
    ADMISSION_RULES,
    OBSERVATION_MODE_STATIC_HTTP,
    SelectionNotAdmissible,
    admitted_page_refs,
    body_digest,
)
from pxapi.domain.sampling_policy import SelectionBudgets
from pxapi.domain.site_discovery import (
    BootstrapFailure,
    DiscoveryObservation,
    DiscoveryReport,
    SourceAttempt,
    SourceOutcome,
)
from pxapi.ports.html_observation import HtmlUnreadable
from pxapi.ports.page_fetch import FetchFailureKind, PageFetchFailure, PageFetchOutcome
from tests.application.test_discover_site import FakeDiscovery
from tests.contracts.support import CONTRACTS

ORIGIN = "https://example.com/"
PAGE_A = "https://example.com/a"
PAGE_B = "https://example.com/b"
PAGE_C = "https://example.com/c"
#: The census order: the seed first, then every other eligible identity in ascending order.
SELECTED = [ORIGIN, PAGE_A, PAGE_B, PAGE_C]

REQUEST = {
    "schema_version": "1.0.0",
    "run_id": "run-1",
    "request_id": "req-1",
    "requested_at": "2026-09-27T12:00:00Z",
    "target_url": ORIGIN,
    "scan_mode": "PUBLIC_NON_INVASIVE",
}

#: Keys whose presence anywhere in the output would make a technical fact a judgement.
VERDICT_KEYS = frozenset(
    {
        "polarity",
        "score",
        "scores",
        "severity",
        "finding",
        "findings",
        "diagnostic_findings",
        "rule_id",
        "business_impact",
        "quality",
        "rating",
        "weight",
        "raw_artifact_ref",
    }
)


def clock() -> datetime:
    return datetime(2026, 9, 27, 12, 0, 0, tzinfo=UTC)


def counting_ids() -> Any:
    counter = iter(range(1, 100_000))
    return lambda: f"id-{next(counter)}"


def report() -> DiscoveryReport:
    return DiscoveryReport(
        target_origin=ORIGIN,
        observations=(
            DiscoveryObservation(ORIGIN, "CANONICAL_SEED"),
            DiscoveryObservation(PAGE_A, "SITEMAP"),
            DiscoveryObservation(PAGE_B, "SITEMAP"),
            DiscoveryObservation(PAGE_C, "SITEMAP"),
        ),
        attempts=(
            SourceAttempt("CANONICAL_SEED", SourceOutcome.USED),
            SourceAttempt("SITEMAP", SourceOutcome.USED),
        ),
    )


def html(title: str = "Leistungen") -> bytes:
    return (
        f"<!doctype html><html><head><title>{title}</title>"
        '<meta name="description" content="Was wir tun."></head><body>x</body></html>'
    ).encode()


def response(
    url: str,
    status: int = 200,
    body: bytes | None = None,
    content_type: str = "text/html; charset=utf-8",
    truncated: bool = False,
    undecodable: bool = False,
    redirect_count: int = 0,
) -> PageFetchOutcome:
    return PageFetchOutcome(
        final_url=url,
        status_code=status,
        content_type=content_type,
        x_robots_tag=(),
        is_https=url.startswith("https://"),
        redirect_count=redirect_count,
        body=html() if body is None else body,
        truncated=truncated,
        declared_charset="utf-8",
        undecodable=undecodable,
    )


@dataclass
class FakeFetcher:
    """A ``PageFetcher`` answering per URL, a normal page by default, recording every call."""

    results: dict[str, Any] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def fetch(self, url: str) -> Any:
        self.calls.append(url)
        value = self.results.get(url)
        if isinstance(value, Exception):
            raise value
        return response(url) if value is None else value


class Tampered:
    """A discovery use case whose envelope is altered before acquisition sees it."""

    def __init__(self, inner: Any, tamper: Any) -> None:
        self.inner = inner
        self.tamper = tamper

    def run(self, request: dict[str, Any]) -> dict[str, Any]:
        envelope = self.inner.run(request)
        self.tamper(envelope)
        return envelope


def build(
    fetcher: FakeFetcher,
    budget: int | None = None,
    *,
    new_id: Any = None,
    read: Any = read_html,
    tamper: Any = None,
    discovery_report: DiscoveryReport | None = None,
    observer_class: type[StaticPageObserver] = StaticPageObserver,
) -> AcquireSelectedPages:
    ids = new_id or counting_ids()
    discover: Any = DiscoverSite(
        FakeDiscovery(discovery_report or report()),
        clock,
        ids,
        SelectionBudgets(max_selected_pages=budget),
    )
    if tamper is not None:
        discover = Tampered(discover, tamper)
    observer = observer_class(
        read_html=read, new_id=ids, max_text_length=CONTRACTS.max_single_line_text()
    )
    return AcquireSelectedPages(discover, fetcher, observer, clock, ids)


def run(fetcher: FakeFetcher | None = None, budget: int | None = None, **kwargs: Any) -> Any:
    return build(fetcher or FakeFetcher(), budget, **kwargs).run(dict(REQUEST))


def record_for(envelope: dict[str, Any], url_key: str) -> dict[str, Any]:
    (found,) = [r for r in envelope["page_acquisitions"] if r["url_key"] == url_key]
    return found


def measurements_of(envelope: dict[str, Any], url_key: str) -> dict[str, dict[str, Any]]:
    refs = set(record_for(envelope, url_key)["measurement_refs"])
    return {m["metric_id"]: m for m in envelope["measurements"] if m["measurement_id"] in refs}


def reasons_of(envelope: dict[str, Any], url_key: str) -> set[str | None]:
    return {
        m["assessment"].get("not_assessed_reason")
        for m in measurements_of(envelope, url_key).values()
    }


def keys_anywhere(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        found |= set(value)
        for item in value.values():
            found |= keys_anywhere(item)
    elif isinstance(value, list):
        for item in value:
            found |= keys_anywhere(item)
    return found


# --- canaries --------------------------------------------------------------------------------


def test_the_verdict_scan_finds_a_planted_key() -> None:
    assert keys_anywhere({"a": [{"polarity": "NEGATIVE"}]}) & VERDICT_KEYS == {"polarity"}


def test_the_frozen_report_selects_four_pages_under_no_budget() -> None:
    envelope = run()
    assert [s["url_key"] for s in envelope["sampling_manifest"]["selections"]] == SELECTED


# --- the manifest is the population ---------------------------------------------------------


def test_every_selected_page_is_attempted_once_and_recorded_once_in_rank_order() -> None:
    fetcher = FakeFetcher()
    envelope = run(fetcher)

    assert envelope["analysis_run_state"]["state"] == "SUCCEEDED"
    assert fetcher.calls == SELECTED
    assert [r["url_key"] for r in envelope["page_acquisitions"]] == SELECTED
    assert invalid_documents(CONTRACTS, envelope) == []
    stages = [(s["stage_id"], s["status"]) for s in envelope["stage_executions"]]
    assert stages == [
        ("SITE_DISCOVERY", "SUCCEEDED"),
        ("SAMPLING_PLAN", "SUCCEEDED"),
        (PAGE_ACQUISITION_STAGE, "SUCCEEDED"),
    ]


def test_the_declared_budget_is_the_manifest_s_and_nothing_truncates_further() -> None:
    fetcher = FakeFetcher()
    envelope = run(fetcher, budget=2)
    manifest = envelope["sampling_manifest"]

    assert manifest["budgets"] == {"max_selected_pages": 2}
    assert manifest["selection_complete"] is False
    assert manifest["incompleteness"] == {"cause": "SELECTION_BUDGET_EXHAUSTED"}
    assert {"reason": "SELECTION_BUDGET_EXHAUSTED", "candidate_count": 2} in manifest["exclusions"]
    # Exactly the selected population: every selection attempted, nothing else attempted.
    assert fetcher.calls == [ORIGIN, PAGE_A]
    assert [r["url_key"] for r in envelope["page_acquisitions"]] == [ORIGIN, PAGE_A]
    assert invalid_documents(CONTRACTS, envelope) == []


def test_a_budget_larger_than_the_population_selects_everything_and_says_complete() -> None:
    fetcher = FakeFetcher()
    envelope = run(fetcher, budget=10)
    assert envelope["sampling_manifest"]["selection_complete"] is True
    assert "incompleteness" not in envelope["sampling_manifest"]
    assert fetcher.calls == SELECTED


# --- page-scoped linkage ----------------------------------------------------------------------


def test_every_record_binds_the_manifest_run_and_this_producer() -> None:
    envelope = run()
    manifest = envelope["sampling_manifest"]
    for record in envelope["page_acquisitions"]:
        assert record["run_id"] == REQUEST["run_id"]
        assert record["sampling_manifest_ref"] == manifest["sampling_manifest_id"]
        assert record["sampling_manifest_output_digest"] == manifest["output_digest"]
        assert record["observation_mode"] == OBSERVATION_MODE_STATIC_HTTP
        assert record["acquisition_method"] == ACQUISITION_METHOD
        assert record["acquisition_method_version"] == ACQUISITION_METHOD_VERSION
        assert "raw_artifact_ref" not in record


def test_every_evidence_resolves_through_one_measurement_to_exactly_one_page() -> None:
    envelope = run()
    owner = {
        ref: record["url_key"]
        for record in envelope["page_acquisitions"]
        for ref in record["measurement_refs"]
    }
    measured = {m["measurement_id"]: m for m in envelope["measurements"]}
    assert set(owner) == set(measured), "every measurement is owned, and only those"

    for item in envelope["website_evidence"]:
        (ref,) = item["measurement_refs"]
        page = owner[ref]
        assert item["source_url"] == measured[ref]["source_url"]
        assert page in SELECTED
    counts = [len(r["measurement_refs"]) for r in envelope["page_acquisitions"]]
    assert counts == [len(PAGE_METRICS)] * len(SELECTED)


def test_the_seed_uses_the_same_generic_profile_as_every_other_page() -> None:
    envelope = run()
    profiles = {url_key: sorted(measurements_of(envelope, url_key)) for url_key in SELECTED}
    assert len({tuple(metrics) for metrics in profiles.values()}) == 1
    assert "HOMEPAGE_GENERIC_NOINDEX_PRESENT" not in profiles[ORIGIN]
    assert {m["collector"] for m in envelope["measurements"]} == {STATIC_PAGE_COLLECTOR}


def test_a_received_response_carries_its_transport_facts_and_decoded_body_digest() -> None:
    envelope = run(FakeFetcher({PAGE_A: response(PAGE_A + "/", redirect_count=1)}))
    record = record_for(envelope, PAGE_A)
    assert record["acquisition_outcome"] == "RESPONSE_RECEIVED"
    assert record["http_status"] == 200
    assert record["final_url_key"] == PAGE_A + "/"
    assert record["redirect_count"] == 1
    assert record["body_truncated"] is False
    assert record["body_decoded"] is True
    assert record["body_digest"] == body_digest(html())


# --- neutral per-page containment ---------------------------------------------------------------


def test_mixed_outcomes_are_contained_per_page_and_the_run_still_succeeds() -> None:
    fetcher = FakeFetcher(
        {
            PAGE_A: response(PAGE_A, status=404, body=html("Seite nicht gefunden")),
            PAGE_B: PageFetchFailure(FetchFailureKind.TIMEOUT),
            PAGE_C: PageFetchFailure(FetchFailureKind.DNS_FAILURE),
        }
    )
    envelope = run(fetcher)

    assert envelope["analysis_run_state"]["state"] == "SUCCEEDED"
    assert fetcher.calls == SELECTED
    outcomes = [r["acquisition_outcome"] for r in envelope["page_acquisitions"]]
    assert outcomes == ["RESPONSE_RECEIVED", "RESPONSE_RECEIVED", "TIMEOUT", "DNS_FAILURE"]
    assert invalid_documents(CONTRACTS, envelope) == []

    # The sibling that worked keeps its truthful facts.
    seed = measurements_of(envelope, ORIGIN)
    assert seed[Metric.PAGE_TITLE.value]["result"]["text_value"] == "Leistungen"
    assert reasons_of(envelope, PAGE_B) == {"TIMEOUT"}
    assert reasons_of(envelope, PAGE_C) == {NOT_ASSESSED_FOR[FetchFailureKind.DNS_FAILURE]}
    for url_key in (PAGE_B, PAGE_C):
        assert "http_status" not in record_for(envelope, url_key)
    assert keys_anywhere(envelope) & VERDICT_KEYS == set()


@pytest.mark.parametrize("status", [404, 410, 500, 503])
def test_a_non_2xx_error_document_is_never_read_as_page_content(status: int) -> None:
    body = html("Fehlerseite des Servers")
    envelope = run(FakeFetcher({PAGE_A: response(PAGE_A, status=status, body=body)}))
    record = record_for(envelope, PAGE_A)
    facts = measurements_of(envelope, PAGE_A)

    assert record["acquisition_outcome"] == "RESPONSE_RECEIVED"
    assert record["http_status"] == status
    assert facts[Metric.HTTP_STATUS.value]["result"]["integer_value"] == status
    for metric in (
        Metric.PAGE_TITLE,
        Metric.PAGE_TITLE_PRESENT,
        Metric.META_DESCRIPTION,
        Metric.CANONICAL_URL,
        Metric.META_ROBOTS_GENERIC_NOINDEX_PRESENT,
    ):
        assert facts[metric.value]["assessment"] == {
            "not_assessed_reason": NON_SUCCESS_NOT_ASSESSED
        }
    assert "Fehlerseite" not in json.dumps(envelope)
    assert invalid_documents(CONTRACTS, envelope) == []
    assert keys_anywhere(envelope) & VERDICT_KEYS == set()


@pytest.mark.parametrize("kind", list(FetchFailureKind), ids=lambda kind: kind.value)
def test_every_fetch_failure_kind_becomes_a_truthful_neutral_record(
    kind: FetchFailureKind,
) -> None:
    fetcher = FakeFetcher({url: PageFetchFailure(kind) for url in SELECTED})
    envelope = run(fetcher)

    assert envelope["analysis_run_state"]["state"] == "SUCCEEDED"
    assert fetcher.calls == SELECTED
    for url_key in SELECTED:
        record = record_for(envelope, url_key)
        assert record["acquisition_outcome"] == kind.value
        assert "http_status" not in record and "body_digest" not in record
        assert reasons_of(envelope, url_key) == {NOT_ASSESSED_FOR[kind]}
    assert invalid_documents(CONTRACTS, envelope) == []
    assert keys_anywhere(envelope) & VERDICT_KEYS == set()


def test_a_truncated_body_is_flagged_and_still_digested() -> None:
    envelope = run(FakeFetcher({PAGE_A: response(PAGE_A, truncated=True)}))
    record = record_for(envelope, PAGE_A)
    assert record["body_truncated"] is True
    assert record["body_digest"] == body_digest(html())
    assert invalid_documents(CONTRACTS, envelope) == []


def test_an_undecodable_body_carries_no_digest_and_no_document_facts() -> None:
    envelope = run(FakeFetcher({PAGE_A: response(PAGE_A, body=b"", undecodable=True)}))
    record = record_for(envelope, PAGE_A)
    assert record["body_decoded"] is False
    assert "body_digest" not in record
    title = measurements_of(envelope, PAGE_A)[Metric.PAGE_TITLE.value]
    assert title["assessment"] == {"not_assessed_reason": "RUNTIME_ERROR"}
    assert invalid_documents(CONTRACTS, envelope) == []


def test_an_unsupported_media_type_is_not_applicable_rather_than_absent() -> None:
    pdf = response(PAGE_A, body=b"%PDF-1.7", content_type="application/pdf")
    envelope = run(FakeFetcher({PAGE_A: pdf}))
    title = measurements_of(envelope, PAGE_A)[Metric.PAGE_TITLE.value]
    assert title["assessment"] == {"collection_mode": "OBSERVED", "result_state": "NOT_APPLICABLE"}
    assert invalid_documents(CONTRACTS, envelope) == []


def test_a_parser_failure_is_our_runtime_and_is_contained_to_the_documents_facts() -> None:
    def broken(body: bytes, charset: str | None) -> Any:
        raise HtmlUnreadable("the document could not be processed")

    envelope = run(read=broken)
    assert envelope["analysis_run_state"]["state"] == "SUCCEEDED"
    for url_key in SELECTED:
        assert record_for(envelope, url_key)["acquisition_outcome"] == "RESPONSE_RECEIVED"
        facts = measurements_of(envelope, url_key)
        assert facts[Metric.PAGE_TITLE.value]["assessment"] == {
            "not_assessed_reason": "RUNTIME_ERROR"
        }
        assert facts[Metric.HTTP_STATUS.value]["assessment"]["result_state"] == "KNOWN"
    assert invalid_documents(CONTRACTS, envelope) == []


def test_a_redirect_ending_at_a_url_with_no_identity_is_an_invalid_redirect() -> None:
    unkeyable = "https://example.com/a\\b"
    envelope = run(FakeFetcher({PAGE_A: response(unkeyable, redirect_count=1)}))
    record = record_for(envelope, PAGE_A)
    assert record["acquisition_outcome"] == "INVALID_REDIRECT"
    assert "final_url_key" not in record and "http_status" not in record
    assert reasons_of(envelope, PAGE_A) == {NOT_ASSESSED_FOR[FetchFailureKind.INVALID_REDIRECT]}
    assert invalid_documents(CONTRACTS, envelope) == []


# --- determinism -------------------------------------------------------------------------------


def test_one_frozen_acquisition_input_serialises_to_the_same_result_twice() -> None:
    def frozen() -> FakeFetcher:
        return FakeFetcher(
            {
                PAGE_A: response(PAGE_A, status=404),
                PAGE_B: PageFetchFailure(FetchFailureKind.DNS_FAILURE),
            }
        )

    first = json.dumps(run(frozen()), sort_keys=True)
    second = json.dumps(run(frozen()), sort_keys=True)
    assert first == second


def test_the_replay_canary_sees_a_different_input() -> None:
    """Canary: the replay comparison is not vacuous — a different body changes the result."""
    changed = FakeFetcher({PAGE_A: response(PAGE_A, body=html("Anders"))})
    assert json.dumps(run(), sort_keys=True) != json.dumps(run(changed), sort_keys=True)


# --- admission before any fetch ------------------------------------------------------------------


def _unknown(envelope: dict[str, Any]) -> None:
    envelope["sampling_manifest"]["selections"][1]["url_key"] = "https://example.com/zzz"


def _duplicate(envelope: dict[str, Any]) -> None:
    selections = envelope["sampling_manifest"]["selections"]
    selections[2]["url_key"] = selections[1]["url_key"]


def _unbound(envelope: dict[str, Any]) -> None:
    envelope["sampling_manifest"]["inventory_output_digest"] = "sha256:" + "f" * 64


def _stale_digest(envelope: dict[str, Any]) -> None:
    envelope["sampling_manifest"]["output_digest"] = "sha256:" + "e" * 64


def _other_run(envelope: dict[str, Any]) -> None:
    envelope["sampling_manifest"]["run_id"] = "run-other"


def _no_selection(envelope: dict[str, Any]) -> None:
    del envelope["sampling_manifest"]


def _empty_selection(envelope: dict[str, Any]) -> None:
    envelope["sampling_manifest"]["selections"] = []


def _altered_inventory(envelope: dict[str, Any]) -> None:
    envelope["site_inventory"]["candidates"].pop()


ADMISSION_CASES = {
    "empty_selection": (_empty_selection, ("/selections", "selection_present")),
    "altered_inventory": (
        _altered_inventory,
        ("/inventory_output_digest", "inventory_digest_reproduces"),
    ),
    "unknown_page_ref": (_unknown, ("/selections/1", "selection_is_an_inventory_candidate")),
    "duplicate_page_ref": (_duplicate, ("/selections/2", "unique_selected_url_key")),
    "unbound_inventory": (_unbound, ("/inventory_ref", "manifest_binds_inventory")),
    "stale_manifest_digest": (_stale_digest, ("/output_digest", "manifest_digests_reproduce")),
    "other_run": (_other_run, ("/run_id", "manifest_binds_run")),
    "missing_manifest": (_no_selection, ("", "manifest_binds_inventory")),
}


@pytest.mark.parametrize("case", sorted(ADMISSION_CASES))
def test_an_inadmissible_selection_fails_the_run_before_any_fetch(case: str) -> None:
    tamper, _expected = ADMISSION_CASES[case]
    fetcher = FakeFetcher()
    envelope = run(fetcher, tamper=tamper)

    assert fetcher.calls == []
    assert envelope["analysis_run_state"]["state"] == "FAILED"
    assert envelope["analysis_run_state"]["failure"] == {"code": SELECTION_NOT_ADMISSIBLE_CODE}
    assert envelope["stage_executions"][-1]["stage_id"] == PAGE_ACQUISITION_STAGE
    assert envelope["stage_executions"][-1]["status"] == "FAILED"
    assert "sampling_manifest" not in envelope
    assert "site_inventory" in envelope
    assert not {"page_acquisitions", "measurements", "website_evidence"} & set(envelope)
    assert invalid_documents(CONTRACTS, envelope) == []


@pytest.mark.parametrize("case", sorted(ADMISSION_CASES))
def test_admission_names_the_rule_each_defect_breaks(case: str) -> None:
    tamper, expected = ADMISSION_CASES[case]
    envelope = build(FakeFetcher()).discover.run(dict(REQUEST))
    tamper(envelope)
    with pytest.raises(SelectionNotAdmissible) as refused:
        admitted_page_refs(
            envelope.get("sampling_manifest"), envelope["site_inventory"], REQUEST["run_id"]
        )
    assert expected in refused.value.keys


def test_every_admission_rule_has_a_counterexample() -> None:
    covered = {rule for _tamper, (_pointer, rule) in ADMISSION_CASES.values()}
    assert set(ADMISSION_RULES) <= covered


def test_an_untampered_selection_is_admitted_in_rank_order() -> None:
    """Canary: the admission gate accepts what the producer actually emits."""
    envelope = build(FakeFetcher()).discover.run(dict(REQUEST))
    admitted = admitted_page_refs(
        envelope["sampling_manifest"], envelope["site_inventory"], REQUEST["run_id"]
    )
    assert admitted == tuple(SELECTED)


def test_a_failed_discovery_is_returned_as_is_and_nothing_is_fetched() -> None:
    fetcher = FakeFetcher()
    failed = DiscoveryReport(None, bootstrap_failure=BootstrapFailure.UNREACHABLE)
    envelope = run(fetcher, discovery_report=failed)
    assert fetcher.calls == []
    assert envelope["analysis_run_state"]["state"] == "FAILED"
    assert all(s["stage_id"] != PAGE_ACQUISITION_STAGE for s in envelope["stage_executions"])
    assert not {"page_acquisitions", "measurements", "website_evidence"} & set(envelope)


# --- our own defects stay visible ------------------------------------------------------------


def test_a_document_set_breaking_a_producer_invariant_fails_the_run_and_is_withheld() -> None:
    fetcher = FakeFetcher()
    envelope = run(fetcher, new_id=lambda: "id-1")

    assert fetcher.calls == SELECTED
    assert envelope["analysis_run_state"]["state"] == "FAILED"
    assert envelope["analysis_run_state"]["failure"] == {"code": ACQUISITION_WITHHELD_CODE}
    assert envelope["stage_executions"][-1]["status"] == "FAILED"
    assert "sampling_manifest" in envelope
    assert not {"page_acquisitions", "measurements", "website_evidence"} & set(envelope)
    assert invalid_documents(CONTRACTS, envelope) == []


class RaisingObserver(StaticPageObserver):
    """An observer with a defect of ours on one page."""

    def observe(self, run_id: str, url_key: str, result: Any, observed_at: str) -> Any:
        if url_key == PAGE_B:
            raise KeyError("a defect in this service")
        return super().observe(run_id, url_key, result, observed_at)


def test_an_observation_that_raises_is_our_defect_and_never_a_page_outcome() -> None:
    envelope = run(observer_class=RaisingObserver)
    assert envelope["analysis_run_state"]["failure"] == {"code": ACQUISITION_WITHHELD_CODE}
    assert "page_acquisitions" not in envelope
    assert invalid_documents(CONTRACTS, envelope) == []


#: Fetch-port behaviour outside the port contract, which is outcomes and never exceptions.
PORT_CONTRACT_BREACHES = {
    "raises": RuntimeError("the fetch path broke"),
    "returns_text": "not an outcome",
    "returns_dict": {"status": 200},
}


@pytest.mark.parametrize("case", sorted(PORT_CONTRACT_BREACHES))
def test_a_fetch_port_contract_breach_fails_the_run_and_withholds_every_page(case: str) -> None:
    """D-20-D: a fetcher that raises or returns a foreign shape is our defect, not a site fact.

    It fails the run even though its sibling pages were fetched successfully, and no page
    document — not even a sibling's — is emitted, exactly as for an observer or invariant defect.
    """
    fetcher = FakeFetcher({PAGE_B: PORT_CONTRACT_BREACHES[case]})
    envelope = run(fetcher)

    assert envelope["analysis_run_state"]["state"] == "FAILED"
    assert envelope["analysis_run_state"]["failure"] == {"code": ACQUISITION_WITHHELD_CODE}
    assert envelope["stage_executions"][-1]["stage_id"] == PAGE_ACQUISITION_STAGE
    assert envelope["stage_executions"][-1]["status"] == "FAILED"
    assert not {"page_acquisitions", "measurements", "website_evidence"} & set(envelope)
    assert "RUNTIME_ERROR" not in json.dumps(envelope)
    assert invalid_documents(CONTRACTS, envelope) == []


def test_the_same_pages_with_expected_failures_only_still_succeed() -> None:
    """Canary for the test above: replacing the breach by an expected outcome is contained."""
    fetcher = FakeFetcher({PAGE_B: PageFetchFailure(FetchFailureKind.CONNECTION_FAILURE)})
    envelope = run(fetcher)
    assert envelope["analysis_run_state"]["state"] == "SUCCEEDED"
    assert record_for(envelope, PAGE_B)["acquisition_outcome"] == "CONNECTION_FAILURE"
    assert record_for(envelope, PAGE_C)["acquisition_outcome"] == "RESPONSE_RECEIVED"
