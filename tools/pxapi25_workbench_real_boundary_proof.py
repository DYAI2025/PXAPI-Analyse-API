"""PXAPI-25 real-boundary proof: one real multi-page run operated through the Workbench.

Run it from a clean checkout of the exact candidate SHA, in the locked environment with the
``browser`` group::

    uv sync --locked --group browser
    uv run --no-sync python tools/pxapi25_workbench_real_boundary_proof.py [--channel chrome]

It is network-dependent evidence and deliberately **not** a push-CI test. It

1. records the checkout's exact ``HEAD`` and refuses a checkout with tracked modifications, and
   refuses to run if the imported ``pxapi`` package is not this checkout's ``src/pxapi``;
2. serves the **production** Workbench (``create_workbench_app()`` with no test seams: the
   strict target policy, the real discovery, fetcher and observer) on a free loopback port;
3. drives a real Chromium through the operator journey: start page → URL
   ``https://www.rfc-editor.org/`` and an explicit budget of 3 → the real synchronous run → the
   result page → every selected page opened in the Evidence Inspector → the validation section;
   it fails if any script element, event-handler attribute or dialog appears;
4. downloads the canonical artifact bundle and the validation receipt *through the browser*, and
   reads them back independently of the adapter: every canonical document is validated against
   its registered contract, the page documents against the producer invariants, the bundle
   digest is recomputed and compared with the receipt, and the receipt is validated against its
   contract and the receipt rules;
5. writes everything under ``--output-dir`` (default ``.proof-output/pxapi25-workbench-real-
   boundary``, untracked): ``proof-receipt.json``, the downloaded files, the extracted canonical
   documents and full-page screenshots at a normal and a narrow viewport.

The validation outcome of the analysed run is **recorded, not required**: with a budget of 3 the
selection is expected to be incomplete, which blocks a release without being a website verdict.
The proof passes when the journey, the downloads and the independent read-back all hold.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGET = "https://www.rfc-editor.org/"
BUDGET = 3
DEFAULT_OUTPUT = ROOT / ".proof-output" / "pxapi25-workbench-real-boundary"
RUN_TIMEOUT_MS = 15 * 60 * 1000
NORMAL = {"width": 1280, "height": 900}
NARROW = {"width": 375, "height": 812}


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def checkout_facts(allow_dirty: bool) -> dict[str, Any]:
    head = git("rev-parse", "HEAD")
    modified = git("status", "--porcelain", "--untracked-files=no").splitlines()
    if modified and not allow_dirty:
        raise SystemExit(f"refusing: tracked modifications in the checkout: {modified}")
    import pxapi

    package = Path(pxapi.__file__).resolve().parent
    if package != (ROOT / "src" / "pxapi").resolve():
        raise SystemExit(f"refusing: pxapi imported from {package}, not this checkout")
    return {"head": head, "tracked_modifications": modified, "pxapi_package": str(package)}


class Served:
    """The production Workbench behind uvicorn on a free loopback port."""

    def __init__(self) -> None:
        import uvicorn

        from pxapi.adapters.inbound.workbench import create_workbench_app

        self.app = create_workbench_app()
        self.server = uvicorn.Server(
            uvicorn.Config(self.app, host="127.0.0.1", port=0, log_level="warning")
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self) -> Served:
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        if not self.server.started:
            raise SystemExit("uvicorn did not start")
        port = self.server.servers[0].sockets[0].getsockname()[1]
        self.base = f"http://127.0.0.1:{port}"
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)


def inert(page: Any) -> list[str]:
    """Problems if anything executable reached the page."""
    problems = []
    if page.locator("script").count():
        problems.append("script element present")
    handlers = page.evaluate(
        "[...document.querySelectorAll('*')].flatMap(e => [...e.attributes])"
        ".filter(a => a.name.startsWith('on')).map(a => a.name)"
    )
    if handlers:
        problems.append(f"event-handler attributes present: {handlers}")
    return problems


def read_back(archive: bytes, receipt_bytes: bytes) -> dict[str, Any]:
    """Independent consumer of the downloaded files: contracts, invariants, digest, receipt."""
    from pxapi.adapters.contracts.registry import ContractRegistry, loads_json
    from pxapi.adapters.inbound.workbench import read_archive
    from pxapi.application.validate_analysis_run import (
        CANONICAL_MEMBERS,
        RECEIPT_CONTRACT,
        RECEIPT_FILE,
        bundle_digest,
    )
    from pxapi.domain.page_acquisition import acquisition_violations
    from pxapi.domain.run_validation import receipt_rule_violations

    registry = ContractRegistry(ROOT / "contracts" / "v1")
    files = read_archive(archive)
    problems: list[str] = []
    documents: dict[str, Any] = {}
    counts: dict[str, int] = {}
    for member, spec in CANONICAL_MEMBERS.items():
        if spec.file_name not in files:
            problems.append(f"{spec.file_name}: missing from the bundle")
            continue
        value = loads_json(files[spec.file_name].decode("utf-8"))
        documents[member] = value
        items = value if spec.plural else [value]
        counts[member] = len(items)
        for index, document in enumerate(items):
            found = registry.validate(spec.contract, document)
            if found:
                problems.append(f"{spec.file_name}/{index}: {len(found)} contract violation(s)")
    unexpected = sorted(
        set(files) - {m.file_name for m in CANONICAL_MEMBERS.values()} - {RECEIPT_FILE}
    )
    problems += [f"{name}: not part of the bundle" for name in unexpected]

    if "sampling_manifest" in documents and "page_acquisitions" in documents:
        found = acquisition_violations(
            documents["page_acquisitions"],
            documents["sampling_manifest"],
            documents.get("measurements", []),
            documents.get("website_evidence", []),
        )
        problems += [f"producer invariant {v.pointer} [{v.rule}]" for v in found]

    receipt = loads_json(receipt_bytes.decode("utf-8"))
    if files.get(RECEIPT_FILE) != receipt_bytes:
        problems.append("the separately downloaded receipt differs from the bundled one")
    if registry.validate(RECEIPT_CONTRACT, receipt):
        problems.append("the receipt fails its contract")
    rules = receipt_rule_violations(receipt)
    problems += [f"receipt rule {v.pointer} [{v.rule}]" for v in rules]
    canonical = {name: content for name, content in files.items() if name != RECEIPT_FILE}
    recomputed = bundle_digest(canonical)
    if recomputed != receipt.get("artifact_bundle_digest"):
        problems.append("the recomputed bundle digest differs from the receipt's")
    return {
        "files": sorted(files),
        "document_counts": counts,
        "recomputed_bundle_digest": recomputed,
        "receipt": receipt,
        "documents": documents,
        "problems": problems,
    }


def journey(base: str, output: Path, channel: str | None) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    evidence: dict[str, Any] = {"target": TARGET, "budget": BUDGET, "problems": []}
    dialogs: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=channel, headless=True)
        evidence["browser"] = f"{channel or 'chromium'} {browser.version}"
        context = browser.new_context(viewport=NORMAL, accept_downloads=True)
        page = context.new_page()
        page.on("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.dismiss()))

        page.goto(f"{base}/operator")
        page.get_by_label("Target URL").fill(TARGET)
        page.get_by_label("Maximum selected pages").fill(str(BUDGET))
        started = time.monotonic()
        with page.expect_navigation(url=f"{base}/operator/runs/*", timeout=RUN_TIMEOUT_MS):
            page.get_by_role("button", name="Start analysis").click()
        evidence["run_seconds"] = round(time.monotonic() - started, 1)
        evidence["result_url"] = page.url.replace(base, "")
        evidence["run_id"] = page.url.rsplit("/", 1)[1]

        overview = page.locator("#overview").inner_text()
        evidence["overview_mentions_target"] = TARGET in overview
        details = page.locator("details.page-evidence")
        evidence["pages_in_evidence_inspector"] = details.count()
        opened = []
        for index in range(details.count()):
            block = details.nth(index)
            block.locator("summary").click()
            opened.append(
                {
                    "summary": block.locator("summary").inner_text(),
                    "open": block.get_attribute("open") is not None,
                    "measurement_rows": block.locator("tbody tr").count(),
                }
            )
        evidence["evidence_inspector"] = opened
        evidence["validation_section"] = page.locator("#validation").inner_text()[:2000]
        evidence["limitations_section"] = page.locator("#limitations").inner_text()[:2000]
        evidence["problems"] += inert(page)
        page.screenshot(path=str(output / "result-normal.png"), full_page=True)

        with page.expect_download() as bundle_info:
            page.get_by_role("link", name="Download the canonical artifact bundle (zip)").click()
        bundle_path = output / "artifacts.zip"
        bundle_info.value.save_as(str(bundle_path))
        with page.expect_download() as receipt_info:
            page.get_by_role("link", name="Download the validation receipt").click()
        receipt_path = output / "analysis-validation-receipt.json"
        receipt_info.value.save_as(str(receipt_path))

        page.reload()
        evidence["reload_keeps_the_result"] = page.locator("#overview").inner_text() == overview

        narrow = browser.new_context(viewport=NARROW).new_page()
        narrow.goto(page.url)
        evidence["narrow_no_horizontal_scroll"] = narrow.evaluate(
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
        )
        narrow.screenshot(path=str(output / "result-narrow.png"), full_page=True)
        browser.close()

    evidence["dialogs"] = dialogs
    if dialogs:
        evidence["problems"].append(f"dialogs opened: {dialogs}")
    evidence["bundle_bytes"] = bundle_path.stat().st_size
    return evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--channel", default=None, help="e.g. 'chrome' for an installed Chrome")
    parser.add_argument("--allow-dirty", action="store_true")
    arguments = parser.parse_args(argv)

    facts = checkout_facts(arguments.allow_dirty)
    output: Path = arguments.output_dir
    output.mkdir(parents=True, exist_ok=False)
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    with Served() as served:
        evidence = journey(served.base, output, arguments.channel)
        workbench = served.app.state.workbench
        acquisition = getattr(workbench.acquisition, "__name__", repr(workbench.acquisition))

    bundle = (output / "artifacts.zip").read_bytes()
    receipt_bytes = (output / "analysis-validation-receipt.json").read_bytes()
    readback = read_back(bundle, receipt_bytes)
    documents = readback.pop("documents")
    canonical_dir = output / "canonical"
    canonical_dir.mkdir()
    for member, value in documents.items():
        (canonical_dir / f"{member}.json").write_text(
            json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    receipt = readback["receipt"]
    manifest = documents.get("sampling_manifest") or {}
    records = documents.get("page_acquisitions") or []
    problems = evidence["problems"] + readback["problems"]
    if acquisition != "build_site_acquisition":
        problems.append(
            f"the served workbench did not use the production composition: {acquisition}"
        )
    if not evidence["overview_mentions_target"]:
        problems.append("the result page does not show the target")
    if evidence["pages_in_evidence_inspector"] != len(records):
        problems.append("the evidence inspector does not show every acquired page")
    if not all(item["open"] for item in evidence["evidence_inspector"]):
        problems.append("a page's evidence could not be opened")
    if len(records) < 2:
        problems.append(f"expected a multi-page run, acquired {len(records)} page(s)")
    if not evidence["reload_keeps_the_result"] or not evidence["narrow_no_horizontal_scroll"]:
        problems.append("reload or narrow-viewport check failed")

    proof = {
        "proof": "pxapi25-workbench-real-boundary",
        "started_at": started_at,
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "checkout": facts,
        "python": sys.version.split()[0],
        "served_acquisition": acquisition,
        "journey": evidence,
        "run": {
            "run_id": receipt["run_id"],
            "run_state": receipt.get("run_state"),
            "selection_complete": manifest.get("selection_complete"),
            "incompleteness": manifest.get("incompleteness"),
            "budgets": manifest.get("budgets"),
            "pages": [
                {
                    "url_key": r["url_key"],
                    "acquisition_outcome": r["acquisition_outcome"],
                    "http_status": r.get("http_status"),
                    "measurements": len(r["measurement_refs"]),
                }
                for r in records
            ],
        },
        "validation": {
            "overall_state": receipt["overall_state"],
            "gates": {
                family: {"state": gate["state"], "reasons": [r["code"] for r in gate["reasons"]]}
                for family, gate in receipt["gates"].items()
            },
            "artifact_bundle_digest": receipt["artifact_bundle_digest"],
        },
        "readback": {k: v for k, v in readback.items() if k != "receipt"},
        "problems": problems,
        "verdict": "PASS" if not problems else "FAIL",
    }
    (output / "proof-receipt.json").write_text(
        json.dumps(proof, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: proof[k] for k in ("verdict", "problems", "run", "validation")}, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
