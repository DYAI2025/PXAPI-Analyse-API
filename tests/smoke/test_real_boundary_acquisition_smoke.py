"""The PXAPI-20 multi-page Real-Boundary smoke, opt-in, against one controlled public site.

Skipped unless ``PXAPI_REAL_BOUNDARY_ACQUISITION_URL`` names a target, so the suite and CI stay
network-free: a public site changes between runs, and a verdict depending on that would test the
site rather than this code. Run deliberately, it drives the *real* command line — the production
composition, the shipped ``PublicTargetPolicy``, real DNS and sockets, the real bounds — with an
explicit ``--max-selected-pages`` (``PXAPI_REAL_BOUNDARY_MAX_SELECTED_PAGES``, default 3 for this
harness only; the command itself has no default), writes the artifacts, reads them back, and
asserts the properties that must hold for any public site, never a site's content.

It passes only for a *multi-page* acquisition: at least two distinct Page Refs selected and
acquired, the manifest, the acquisition records and the receipt agreeing on the count, and the
chain WebsiteEvidence -> MeasurementRecord -> PageAcquisitionRecord resolving for at least two
Page Refs. ``PXAPI_REAL_BOUNDARY_OUTPUT_DIR``, when set, must name a directory that does not
exist yet.

What it proves is the tested boundary only: one bounded selection acquired safely into valid,
linked, page-scoped documents. It does not prove complete site coverage, browser rendering,
scoring validity, PDF readiness, production scale or customer value.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from pxapi.adapters.composition import default_registry
from pxapi.adapters.inbound import acquire_cli

TARGET = os.environ.get("PXAPI_REAL_BOUNDARY_ACQUISITION_URL")
BUDGET = os.environ.get("PXAPI_REAL_BOUNDARY_MAX_SELECTED_PAGES", "3")

pytestmark = pytest.mark.skipif(
    not TARGET, reason="opt-in: set PXAPI_REAL_BOUNDARY_ACQUISITION_URL to a public target"
)


def _load(directory: Path, file_name: str) -> object:
    return json.loads((directory / file_name).read_text(encoding="utf-8"))


def test_one_bounded_selection_crosses_the_whole_acquisition_boundary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert TARGET is not None
    assert int(BUDGET) >= 2, "a multi-page proof needs a budget of at least two pages"
    out = Path(os.environ.get("PXAPI_REAL_BOUNDARY_OUTPUT_DIR") or tmp_path / "run")
    argv = [TARGET, "--max-selected-pages", BUDGET, "--output-dir", str(out)]
    assert acquire_cli.main(argv) == 0
    envelope = json.loads(capsys.readouterr().out)

    assert acquire_cli.read_back_problems(out, default_registry(), envelope) == []
    state = _load(out, "analysis-run-state.json")
    inventory = _load(out, "site-inventory.json")
    manifest = _load(out, "sampling-manifest.json")
    records = _load(out, "page-acquisition-records.json")
    measurements = _load(out, "measurement-records.json")
    evidence = _load(out, "website-evidence.json")
    receipt = _load(out, acquire_cli.RECEIPT_FILE)
    assert isinstance(state, dict) and isinstance(inventory, dict) and isinstance(manifest, dict)
    assert isinstance(records, list) and isinstance(measurements, list)
    assert isinstance(evidence, list) and isinstance(receipt, dict)

    run_id = state["run_id"]
    assert state["state"] == "SUCCEEDED", state
    assert receipt["run_id"] == run_id and receipt["run_state"] == "SUCCEEDED"
    assert manifest["run_id"] == run_id and inventory["run_id"] == run_id
    assert manifest["inventory_ref"] == inventory["inventory_id"]
    assert manifest["inventory_output_digest"] == inventory["output_digest"]
    assert manifest["budgets"] == {"max_selected_pages": int(BUDGET)}
    assert len(manifest["selections"]) <= int(BUDGET)
    if manifest["selection_complete"] is False:
        assert manifest["incompleteness"] == {"cause": "SELECTION_BUDGET_EXHAUSTED"}

    # More than one page: at least two distinct Page Refs, and every count agrees.
    ranked = sorted(manifest["selections"], key=lambda s: s["selection_rank"])
    selected = [s["url_key"] for s in ranked]
    assert len(set(selected)) == len(selected) >= 2, selected
    assert [r["url_key"] for r in records] == selected
    assert len({r["url_key"] for r in records}) == len(records) == len(selected)
    assert [row["url_key"] for row in receipt["pages"]] == selected
    assert receipt["sampling_manifest"]["selected_count"] == len(selected)
    assert receipt["document_digests"]["page_acquisitions"]["count"] == len(records)

    measurement_ids = {m["measurement_id"] for m in measurements}
    for document in (*records, *measurements, *evidence):
        assert document["run_id"] == run_id
    for record in records:
        assert record["sampling_manifest_ref"] == manifest["sampling_manifest_id"]
        assert record["sampling_manifest_output_digest"] == manifest["output_digest"]
        assert "raw_artifact_ref" not in record
        assert set(record["measurement_refs"]) <= measurement_ids
    for row in receipt["pages"]:
        assert row["measurement_refs"] or row["measurements_withheld_reason"]
        assert len(row["evidence_refs"]) == len(row["measurement_refs"])

    # Evidence -> measurement -> the one acquisition record naming it, for at least two pages.
    page_of = {ref: r["url_key"] for r in records for ref in r["measurement_refs"]}
    linked: set[str] = set()
    for item in evidence:
        pages = {page_of.get(ref) for ref in item["measurement_refs"]}
        assert len(pages) == 1 and None not in pages, item["evidence_id"]
        linked |= pages
    assert len(linked) >= 2, sorted(linked)
