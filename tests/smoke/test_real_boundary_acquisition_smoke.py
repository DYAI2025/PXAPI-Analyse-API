"""The PXAPI-20 multi-page Real-Boundary smoke, opt-in, against one controlled public site.

Skipped unless ``PXAPI_REAL_BOUNDARY_ACQUISITION_URL`` names a target, so the suite and CI stay
network-free: a public site changes between runs, and a verdict depending on that would test the
site rather than this code. Run deliberately, it drives the *real* command line — the production
composition, the shipped ``PublicTargetPolicy``, real DNS and sockets, the real bounds — with an
explicit ``--max-selected-pages`` (``PXAPI_REAL_BOUNDARY_MAX_SELECTED_PAGES``, default 3 for this
harness only; the command itself has no default), writes the artifacts, reads them back, and
asserts the properties that must hold for any public site, never a site's content.

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
    out = Path(os.environ.get("PXAPI_REAL_BOUNDARY_OUTPUT_DIR") or tmp_path / "run")
    argv = [TARGET, "--max-selected-pages", BUDGET, "--output-dir", str(out)]
    assert acquire_cli.main(argv) == 0
    capsys.readouterr()

    assert acquire_cli.read_back_problems(out, default_registry()) == []
    state = _load(out, "analysis-run-state.json")
    manifest = _load(out, "sampling-manifest.json")
    records = _load(out, "page-acquisition-records.json")
    receipt = _load(out, acquire_cli.RECEIPT_FILE)
    assert isinstance(state, dict) and isinstance(manifest, dict) and isinstance(records, list)
    assert isinstance(receipt, dict)

    assert state["state"] == "SUCCEEDED", state
    assert manifest["budgets"] == {"max_selected_pages": int(BUDGET)}
    assert len(manifest["selections"]) <= int(BUDGET)
    if manifest["selection_complete"] is False:
        assert manifest["incompleteness"] == {"cause": "SELECTION_BUDGET_EXHAUSTED"}
    ranked = sorted(manifest["selections"], key=lambda s: s["selection_rank"])
    assert [r["url_key"] for r in records] == [s["url_key"] for s in ranked]
    for record in records:
        assert record["sampling_manifest_output_digest"] == manifest["output_digest"]
        assert "raw_artifact_ref" not in record
    for row in receipt["pages"]:
        assert row["measurement_refs"] or row["measurements_withheld_reason"]
        assert len(row["evidence_refs"]) == len(row["measurement_refs"])
