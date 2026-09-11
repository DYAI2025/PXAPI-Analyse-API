"""The discovery use case, driven through a fake port: documents, failures and neutrality.

The strongest test here regenerates the registered PXAPI-19.A example documents *from their own
illustrative discovery input* through the production pipeline — admission, canonicalisation,
aggregation, classification, source counts, the census plan and both digest pairs — and
requires the result to equal the registered document. Those examples were written by hand to
illustrate the contracts before any producer existed, so agreement is evidence the producer
implements what the contracts meant rather than what it happens to compute.
"""

from __future__ import annotations

import json
import random
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from pxapi.application import discover_site as use_case
from pxapi.application.discover_site import DiscoverSite
from pxapi.domain.acquisition_digests import manifest_digests
from pxapi.domain.sampling_policy import SelectionBudgets, SelectionPlan
from pxapi.domain.site_discovery import (
    BootstrapFailure,
    DiscoveryObservation,
    DiscoveryReport,
    SourceAttempt,
    SourceOutcome,
)
from tests.acquisition.digests import ILLUSTRATIVE_DISCOVERY_INPUT
from tests.contracts.support import CONTRACTS, load_json

ORIGIN = "https://example.com/"
EXAMPLE_INVENTORY_ID = "inv-01JQ8Z4K2M0000000000000019"
EXAMPLE_RUN_ID = "run-01JQ8Z4K2M0000000000000019"

#: Keys whose presence anywhere in an envelope would mean a technical state became a verdict.
VERDICT_KEYS = frozenset(
    {
        "score",
        "scores",
        "severity",
        "polarity",
        "finding",
        "findings",
        "diagnostic_findings",
        "website_evidence",
        "measurements",
        "weight",
        "penalty",
        "quality",
        "grade",
        "rating",
    }
)


@dataclass
class FakeDiscovery:
    """A ``SiteDiscoveryPort`` that returns one frozen report and records what it was asked."""

    report: DiscoveryReport
    calls: list[str] = field(default_factory=list)

    def discover(self, target_url: str) -> DiscoveryReport:
        self.calls.append(target_url)
        return self.report


def clock_of(*instants: str) -> Any:
    moments: Iterator[datetime] = iter(
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC) for value in instants
    )
    return lambda: next(moments)


def ids_of(*values: str) -> Any:
    supply = iter(values)
    return lambda: next(supply)


def counting_ids() -> Any:
    counter = iter(range(1, 10_000))
    return lambda: f"id-{next(counter)}"


FIXED_CLOCK = clock_of(*["2026-09-11T12:00:00Z"] * 3)


def attempts(**outcomes: str) -> tuple[SourceAttempt, ...]:
    return tuple(SourceAttempt(name, SourceOutcome(value)) for name, value in outcomes.items())


def example_report() -> DiscoveryReport:
    observations = tuple(
        DiscoveryObservation(o["observed_form"], o["source_id"])
        for o in ILLUSTRATIVE_DISCOVERY_INPUT[EXAMPLE_INVENTORY_ID]
    )
    return DiscoveryReport(
        target_origin=ORIGIN,
        observations=observations,
        attempts=attempts(
            CANONICAL_SEED="USED",
            ROBOTS_DECLARATION="USED",
            SITEMAP="USED",
            SAME_ORIGIN_PAGE_LINKS="USED",
        ),
    )


def run(report: DiscoveryReport, budget: int | None = 25, **kwargs: Any) -> dict[str, Any]:
    use = DiscoverSite(
        FakeDiscovery(report),
        kwargs.get("clock", clock_of(*["2026-09-11T12:00:00Z"] * 3)),
        kwargs.get("new_id", counting_ids()),
        SelectionBudgets(max_selected_pages=budget),
    )
    return use.run({"run_id": kwargs.get("run_id", "run-1"), "target_url": ORIGIN})


def canonical(document: dict[str, Any]) -> dict[str, Any]:
    """A document with its order-free collections sorted, for semantic equality."""
    copied = json.loads(json.dumps(document))
    for member, key in (("sources", "source_id"), ("candidates", "url_key")):
        if member in copied:
            copied[member] = sorted(copied[member], key=lambda item, k=key: item[k])
            for item in copied[member]:
                for inner in ("observed_forms", "provenance"):
                    if inner in item:
                        item[inner] = sorted(item[inner])
    return copied


def verdict_keys_in(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        found |= VERDICT_KEYS & set(value)
        for item in value.values():
            found |= verdict_keys_in(item)
    elif isinstance(value, list):
        for item in value:
            found |= verdict_keys_in(item)
    return found


def assert_every_document_satisfies_its_contract(envelope: dict[str, Any]) -> None:
    checks = [("analysis-run-state", envelope["analysis_run_state"])]
    checks += [("stage-execution-record", stage) for stage in envelope["stage_executions"]]
    if "site_inventory" in envelope:
        checks.append(("site-inventory", envelope["site_inventory"]))
    if "sampling_manifest" in envelope:
        checks.append(("sampling-manifest", envelope["sampling_manifest"]))
    for name, document in checks:
        assert CONTRACTS.validate(name, document) == (), (name, CONTRACTS.validate(name, document))


# --- the registered examples, regenerated -----------------------------------------------------


def test_the_producer_regenerates_the_registered_inventory_and_census_from_their_input() -> None:
    envelope = run(
        example_report(),
        clock=clock_of("2026-09-10T08:41:00Z", "2026-09-10T08:41:12Z", "2026-09-10T08:41:19Z"),
        new_id=ids_of(EXAMPLE_INVENTORY_ID, "smf-01JQ8Z4K2M0000000000000019"),
        run_id=EXAMPLE_RUN_ID,
    )
    registered_inventory = load_json(CONTRACTS.path / "examples" / "site-inventory.example.json")
    registered_manifest = load_json(CONTRACTS.path / "examples" / "sampling-manifest.example.json")
    assert canonical(envelope["site_inventory"]) == canonical(registered_inventory)
    assert envelope["sampling_manifest"] == registered_manifest


def test_the_producer_regenerates_the_registered_bounded_census() -> None:
    envelope = run(
        example_report(),
        budget=2,
        clock=clock_of("2026-09-10T08:41:00Z", "2026-09-10T08:41:12Z", "2026-09-10T08:47:02Z"),
        new_id=ids_of(EXAMPLE_INVENTORY_ID, "smf-01JQ8Z4K2M0000000000000023"),
        run_id=EXAMPLE_RUN_ID,
    )
    registered = load_json(
        CONTRACTS.path / "examples" / "sampling-manifest.bounded-selection.example.json"
    )
    assert envelope["sampling_manifest"] == registered


# --- AC1: determinism ---------------------------------------------------------------------


def test_the_same_frozen_input_in_any_order_yields_the_same_documents() -> None:
    base = example_report()
    reference = run(base, new_id=ids_of("inv-a", "smf-a"))
    shuffler = random.Random(19)
    for _ in range(20):
        observations = list(base.observations)
        attempted = list(base.attempts)
        shuffler.shuffle(observations)
        shuffler.shuffle(attempted)
        report = DiscoveryReport(ORIGIN, tuple(observations), tuple(attempted))
        again = run(report, new_id=ids_of("inv-a", "smf-a"))
        assert again["site_inventory"] == reference["site_inventory"]
        assert again["sampling_manifest"] == reference["sampling_manifest"]


def test_a_new_identity_and_instant_change_no_digest_but_the_manifest_input_binding() -> None:
    """Envelopes never participate. ``inventory_ref`` is not this manifest's envelope, though:
    the 19.A classification makes it an *input* of the selection, so a manifest drawn from an
    inventory re-emitted under a new id is bound to that new id. The rebinding below proves the
    reference is the only thing that moved the digest."""
    first = run(example_report(), new_id=ids_of("inv-a", "smf-a"))
    second = run(
        example_report(),
        new_id=ids_of("inv-b", "smf-b"),
        clock=clock_of(*["2031-01-01T00:00:00Z"] * 3),
        run_id="run-other",
    )
    for digest in ("input_digest", "output_digest"):
        assert first["site_inventory"][digest] == second["site_inventory"][digest]
    assert (
        first["sampling_manifest"]["output_digest"] == second["sampling_manifest"]["output_digest"]
    )
    assert first["sampling_manifest"]["input_digest"] != second["sampling_manifest"]["input_digest"]
    rebound = dict(second["sampling_manifest"], inventory_ref="inv-a")
    assert manifest_digests(rebound)[0] == first["sampling_manifest"]["input_digest"]


def test_the_manifest_is_bound_to_the_exact_inventory_it_was_drawn_from() -> None:
    envelope = run(example_report())
    inventory, manifest = envelope["site_inventory"], envelope["sampling_manifest"]
    assert manifest["inventory_ref"] == inventory["inventory_id"]
    assert manifest["inventory_output_digest"] == inventory["output_digest"]


# --- the documents ------------------------------------------------------------------------


def test_every_produced_document_satisfies_its_contract() -> None:
    assert_every_document_satisfies_its_contract(run(example_report()))
    assert_every_document_satisfies_its_contract(run(example_report(), budget=2))


def test_the_canonical_target_seed_exists_and_is_the_origin() -> None:
    inventory = run(example_report())["site_inventory"]
    seeds = [c for c in inventory["candidates"] if c["url_key"] == inventory["target_origin"]]
    assert len(seeds) == 1
    assert "CANONICAL_SEED" in seeds[0]["provenance"]
    assert seeds[0]["eligibility"] == {"state": "ELIGIBLE"}


def test_every_selection_has_a_stratum_a_reason_and_a_stable_identity() -> None:
    manifest = run(example_report())["sampling_manifest"]
    inventory_keys = {c["url_key"] for c in run(example_report())["site_inventory"]["candidates"]}
    for selection in manifest["selections"]:
        assert selection["stratum"] and selection["selection_reason"] in {"SEED", "CENSUS"}
        assert selection["url_key"] in inventory_keys
    ranks = [s["selection_rank"] for s in manifest["selections"]]
    keys = [s["url_key"] for s in manifest["selections"]]
    assert sorted(ranks) == list(range(1, len(ranks) + 1))
    assert len(set(keys)) == len(keys)
    reasons = [e["reason"] for e in manifest["exclusions"]]
    assert len(set(reasons)) == len(reasons)


def test_a_page_the_classifier_cannot_place_is_counted_under_the_neutral_stratum() -> None:
    report = DiscoveryReport(
        ORIGIN,
        (
            DiscoveryObservation(ORIGIN, "CANONICAL_SEED"),
            DiscoveryObservation(ORIGIN + "xyz123", "SAME_ORIGIN_PAGE_LINKS"),
        ),
        attempts(CANONICAL_SEED="USED", SAME_ORIGIN_PAGE_LINKS="USED"),
    )
    envelope = run(report)
    candidate = next(c for c in envelope["site_inventory"]["candidates"] if "xyz" in c["url_key"])
    assert "page_type" not in candidate
    assert candidate["eligibility"] == {"state": "ELIGIBLE"}
    selection = next(
        s for s in envelope["sampling_manifest"]["selections"] if "xyz" in s["url_key"]
    )
    assert selection["stratum"] == "UNCLASSIFIED"


def test_a_budget_bounded_census_names_its_cause_and_its_budget() -> None:
    manifest = run(example_report(), budget=2)["sampling_manifest"]
    assert manifest["mode"] == "CENSUS"
    assert manifest["selection_complete"] is False
    assert manifest["incompleteness"] == {"cause": "SELECTION_BUDGET_EXHAUSTED"}
    assert manifest["budgets"] == {"max_selected_pages": 2}


def test_a_complete_census_carries_no_incompleteness() -> None:
    manifest = run(example_report())["sampling_manifest"]
    assert manifest["selection_complete"] is True
    assert "incompleteness" not in manifest


def test_a_transient_label_leaves_no_trace_in_any_document() -> None:
    report = DiscoveryReport(
        ORIGIN,
        (
            DiscoveryObservation(ORIGIN, "CANONICAL_SEED"),
            DiscoveryObservation(ORIGIN + "seite-7", "SAME_ORIGIN_PAGE_LINKS", "Kontaktformular"),
        ),
        attempts(CANONICAL_SEED="USED", SAME_ORIGIN_PAGE_LINKS="USED"),
    )
    envelope = run(report)
    assert "Kontaktformular" not in json.dumps(envelope)
    page = next(c for c in envelope["site_inventory"]["candidates"] if "seite-7" in c["url_key"])
    assert page["page_type"] == "CONTACT"


def test_a_credential_bearing_observation_is_never_persisted_or_digested() -> None:
    clean = example_report()
    dirty = DiscoveryReport(
        ORIGIN,
        (*clean.observations, DiscoveryObservation("https://user:secret@example.com/x", "SITEMAP")),
        clean.attempts,
    )
    first, second = run(clean, new_id=ids_of("i", "s")), run(dirty, new_id=ids_of("i", "s"))
    assert "secret" not in json.dumps(second)
    assert first["site_inventory"] == second["site_inventory"]


# --- bootstrap failures and withheld documents -------------------------------------------


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (BootstrapFailure.TARGET_REFUSED, "TARGET_NOT_PERMITTED"),
        (BootstrapFailure.UNREACHABLE, "SITE_DISCOVERY_TARGET_UNREACHABLE"),
        (BootstrapFailure.TIMEOUT, "SITE_DISCOVERY_TIMEOUT"),
        (BootstrapFailure.RUNTIME_ERROR, "SITE_DISCOVERY_RUNTIME_ERROR"),
        (None, "SITE_DISCOVERY_BOOTSTRAP_FAILED"),
    ],
)
def test_a_failed_bootstrap_produces_no_inventory_and_no_manifest(
    failure: BootstrapFailure | None, code: str
) -> None:
    envelope = run(DiscoveryReport(None, bootstrap_failure=failure))
    assert "site_inventory" not in envelope and "sampling_manifest" not in envelope
    assert envelope["analysis_run_state"]["state"] == "FAILED"
    assert envelope["analysis_run_state"]["failure"] == {"code": code}
    assert [s["status"] for s in envelope["stage_executions"]] == ["FAILED"]
    assert_every_document_satisfies_its_contract(envelope)


def test_a_report_without_the_seed_is_withheld_rather_than_given_an_invented_one() -> None:
    report = DiscoveryReport(
        ORIGIN,
        (DiscoveryObservation(ORIGIN + "kontakt", "SAME_ORIGIN_PAGE_LINKS"),),
        attempts(SAME_ORIGIN_PAGE_LINKS="USED"),
    )
    envelope = run(report)
    assert "site_inventory" not in envelope
    assert envelope["analysis_run_state"]["failure"] == {"code": "SITE_INVENTORY_NOT_EMITTABLE"}


def test_a_duplicated_source_identity_fails_closed_before_any_document_is_emitted() -> None:
    base = example_report()
    report = DiscoveryReport(
        ORIGIN, base.observations, (*base.attempts, SourceAttempt("SITEMAP", SourceOutcome.ABSENT))
    )
    envelope = run(report)
    assert "site_inventory" not in envelope and "sampling_manifest" not in envelope
    assert envelope["analysis_run_state"]["failure"] == {"code": "SITE_INVENTORY_NOT_EMITTABLE"}


def test_a_source_claiming_no_admission_while_contributing_a_page_fails_closed() -> None:
    base = example_report()
    report = DiscoveryReport(
        ORIGIN,
        base.observations,
        attempts(
            CANONICAL_SEED="USED",
            ROBOTS_DECLARATION="USED",
            SITEMAP="MALFORMED",
            SAME_ORIGIN_PAGE_LINKS="USED",
        ),
    )
    envelope = run(report)
    assert "site_inventory" not in envelope
    assert envelope["analysis_run_state"]["failure"] == {"code": "SITE_INVENTORY_NOT_EMITTABLE"}


def test_a_plan_the_producer_may_not_emit_is_withheld_and_the_inventory_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Counter-mutation for AC3: were the planner ever to draw a sample, nothing would ship."""
    real = use_case.plan_census

    def sampling_planner(*args: Any, **kwargs: Any) -> SelectionPlan:
        plan = real(*args, **kwargs)
        return SelectionPlan(
            "STRATIFIED_SAMPLE",
            plan.selection_complete,
            plan.incompleteness_cause,
            plan.selections,
            plan.exclusions,
            plan.budgets,
        )

    monkeypatch.setattr(use_case, "plan_census", sampling_planner)
    envelope = run(example_report())
    assert "sampling_manifest" not in envelope
    assert "site_inventory" in envelope
    assert envelope["analysis_run_state"]["failure"] == {"code": "SAMPLING_MANIFEST_NOT_EMITTABLE"}
    assert [(s["stage_id"], s["status"]) for s in envelope["stage_executions"]] == [
        ("SITE_DISCOVERY", "SUCCEEDED"),
        ("SAMPLING_PLAN", "FAILED"),
    ]
    assert_every_document_satisfies_its_contract(envelope)


def test_a_provider_origin_in_a_non_canonical_form_is_brought_into_canonical_form() -> None:
    base = example_report()
    envelope = run(DiscoveryReport("https://EXAMPLE.com", base.observations, base.attempts))
    assert envelope["site_inventory"]["target_origin"] == ORIGIN


# --- neutrality ---------------------------------------------------------------------------


NEUTRAL_OUTCOMES = [outcome.value for outcome in SourceOutcome if outcome.value != "USED"]


@pytest.mark.parametrize("outcome", NEUTRAL_OUTCOMES)
def test_no_technical_source_state_produces_a_verdict_of_any_kind(outcome: str) -> None:
    report = DiscoveryReport(
        ORIGIN,
        (DiscoveryObservation(ORIGIN, "CANONICAL_SEED"),),
        attempts(CANONICAL_SEED="USED", ROBOTS_DECLARATION=outcome, SITEMAP=outcome),
    )
    envelope = run(report)
    assert verdict_keys_in(envelope) == set()
    assert envelope["analysis_run_state"]["state"] == "SUCCEEDED"
    assert envelope["sampling_manifest"]["mode"] == "CENSUS"
    assert_every_document_satisfies_its_contract(envelope)


def test_no_failed_run_produces_a_verdict_of_any_kind() -> None:
    for failure in BootstrapFailure:
        assert verdict_keys_in(run(DiscoveryReport(None, bootstrap_failure=failure))) == set()


def test_the_verdict_scan_finds_a_planted_verdict() -> None:
    """Canary: the neutrality walk is proved to see a verdict wherever one is nested."""
    assert verdict_keys_in({"a": [{"b": {"polarity": "NEGATIVE"}}]}) == {"polarity"}


class _ExplodingDiscovery:
    def discover(self, target_url: str) -> DiscoveryReport:
        raise RuntimeError("a provider broke its port contract")


def test_a_provider_that_raises_ends_the_run_as_our_runtime_error() -> None:
    use = DiscoverSite(_ExplodingDiscovery(), FIXED_CLOCK, counting_ids(), SelectionBudgets(25))
    envelope = use.run({"run_id": "run-1", "target_url": ORIGIN})
    assert "site_inventory" not in envelope and "sampling_manifest" not in envelope
    assert envelope["analysis_run_state"]["failure"] == {"code": "SITE_DISCOVERY_RUNTIME_ERROR"}
    assert_every_document_satisfies_its_contract(envelope)


def test_every_bootstrap_failure_has_a_run_failure_code() -> None:
    assert set(use_case.BOOTSTRAP_FAILURE_CODE) == set(BootstrapFailure)
