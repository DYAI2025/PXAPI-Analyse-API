"""The PXAPI-25 real-boundary proof's independent read-back, proved offline.

The proof itself needs a network and a browser and is never a CI test. Its read-back — the part
that decides whether a downloaded bundle and receipt are what they claim — is plain code, so it
is proved here against bundles the Workbench really served, and against tampered copies of them.
The tool is not part of the product package, so it is imported by file path.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from pxapi.adapters.inbound.workbench import archive_of, read_archive
from pxapi.application.validate_analysis_run import RECEIPT_FILE
from tests.adapters.test_workbench import client_for, completed_run

TOOL = Path(__file__).resolve().parents[2] / "tools" / "pxapi25_workbench_real_boundary_proof.py"


def load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pxapi25_workbench_proof", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def served_bundle() -> tuple[bytes, bytes]:
    client = client_for()
    location = completed_run(client, budget="4")
    return (
        client.get(f"{location}/artifacts.zip").content,
        client.get(f"{location}/{RECEIPT_FILE}").content,
    )


def test_a_bundle_the_workbench_served_reads_back_clean(served_bundle: tuple[bytes, bytes]) -> None:
    readback = load_tool().read_back(*served_bundle)
    assert readback["problems"] == []
    assert readback["receipt"]["overall_state"] == "PASS"
    assert readback["document_counts"]["page_acquisitions"] == 4


def test_a_tampered_canonical_file_is_reported(served_bundle: tuple[bytes, bytes]) -> None:
    archive, receipt = served_bundle
    files = read_archive(archive)
    manifest = json.loads(files["sampling-manifest.json"])
    manifest["selection_complete"] = "yes"
    files["sampling-manifest.json"] = json.dumps(manifest).encode()
    problems = load_tool().read_back(archive_of(files), receipt)["problems"]
    assert any("sampling-manifest.json/0" in problem for problem in problems)
    assert "the recomputed bundle digest differs from the receipt's" in problems


def test_a_receipt_that_is_not_the_bundled_one_is_reported(
    served_bundle: tuple[bytes, bytes],
) -> None:
    archive, receipt = served_bundle
    other = json.loads(receipt)
    other["receipt_id"] = "rcp-other"
    problems = load_tool().read_back(archive, json.dumps(other).encode())["problems"]
    assert "the separately downloaded receipt differs from the bundled one" in problems


def test_an_extra_file_in_the_bundle_is_reported(served_bundle: tuple[bytes, bytes]) -> None:
    archive, receipt = served_bundle
    files = dict(read_archive(archive), **{"notes.txt": b"hello"})
    problems = load_tool().read_back(archive_of(files), receipt)["problems"]
    assert "notes.txt: not part of the bundle" in problems


def test_the_tool_targets_the_agreed_site_and_budget() -> None:
    tool = load_tool()
    assert tool.TARGET == "https://www.rfc-editor.org/"
    assert tool.BUDGET == 3
