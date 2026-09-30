"""Frozen multi-page runs for the run-validation tests, and the one validator they are fed to.

Every run here is produced by the real ``AcquireSelectedPages`` over the real ``DiscoverSite``
and the real ``StaticPageObserver``; only the discovery and fetch ports are faked, exactly as in
``tests/application/test_acquire_selected_pages.py``, whose fixtures are reused rather than
restated. A tampered run is a produced run altered afterwards, so every defect a test plants is
a named, one-line change to a document that was genuine a moment before.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

from pxapi.application.validate_analysis_run import ValidateAnalysisRun, build_artifact_bundle
from pxapi.domain.run_validation import GateFamily
from pxapi.domain.site_discovery import DiscoveryReport
from tests.application.test_acquire_selected_pages import (
    REQUEST,
    SELECTED,
    FakeFetcher,
    build,
    report,
)
from tests.contracts.support import CONTRACTS

#: The run every frozen request declares.
RUN_ID: str = REQUEST["run_id"]

#: A budget that covers the frozen population, so the selection is complete.
FULL_BUDGET = len(SELECTED)


def validated_at() -> datetime:
    return datetime(2026, 9, 28, 12, 0, 0, tzinfo=UTC)


def receipt_ids() -> Any:
    counter = iter(range(1, 100_000))
    return lambda: f"rcp-{next(counter)}"


def acquired(
    fetcher: FakeFetcher | None = None,
    budget: int = FULL_BUDGET,
    discovery_report: DiscoveryReport | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """One genuine multi-page run over the frozen site, under a declared budget."""
    use = build(fetcher or FakeFetcher(), budget, discovery_report=discovery_report, **kwargs)
    return use.run(dict(REQUEST))


def validator() -> ValidateAnalysisRun:
    return ValidateAnalysisRun(CONTRACTS, validated_at, receipt_ids())


def validate(
    envelope: dict[str, Any],
    bundle: dict[str, bytes] | None = None,
    *,
    budget: int = FULL_BUDGET,
    run_id: str | None = None,
    submitted: dict[str, Any] = REQUEST,
) -> dict[str, Any]:
    """Validate a run against its own bundle unless a (tampered) one is handed in.

    ``submitted`` is the request the operator submitted — the frozen ``REQUEST`` every genuine
    run here was produced from — and ``run_id`` overrides only its run identity.
    """
    published = build_artifact_bundle(envelope) if bundle is None else bundle
    request = submitted if run_id is None else dict(submitted, run_id=run_id)
    return validator().run(envelope, published, submitted_request=request, declared_budget=budget)


def states(receipt: dict[str, Any]) -> dict[str, str]:
    return {family.value: receipt["gates"][family.value]["state"] for family in GateFamily}


def codes(receipt: dict[str, Any], family: GateFamily) -> list[str]:
    return [item["code"] for item in receipt["gates"][family.value]["reasons"]]


def all_codes(receipt: dict[str, Any]) -> set[str]:
    return {item["code"] for gate in receipt["gates"].values() for item in gate["reasons"]}


def tampered(envelope: dict[str, Any], change: Any) -> dict[str, Any]:
    """A deep copy of a genuine run with one change applied, the original left untouched."""
    altered = copy.deepcopy(envelope)
    change(altered)
    return altered


__all__ = [
    "FULL_BUDGET",
    "RUN_ID",
    "SELECTED",
    "FakeFetcher",
    "acquired",
    "all_codes",
    "codes",
    "receipt_ids",
    "report",
    "states",
    "tampered",
    "validate",
    "validated_at",
    "validator",
]
