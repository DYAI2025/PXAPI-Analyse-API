"""The Operator Workbench in a real browser: the deterministic journey (PXAPI-25).

A real Chromium, driven by Playwright, operates a real uvicorn server running the Workbench
adapter. Only the analysis is deterministic: the adapter's acquisition factory is the fake-port
runtime of ``tests/adapters/test_workbench.py``, so every page, outcome and hostile string is
known in advance. The real-boundary journey against a public site is a separate proof
(``tools/pxapi25_workbench_real_boundary_proof.py``) and never a push-CI test.

These tests need the ``browser`` dependency group (``uv sync --locked --group browser``) and a
browser. Without Playwright they are skipped, **unless** ``PXAPI_BROWSER_TESTS=required`` is set —
as the dedicated CI job sets it — in which case a missing Playwright is an error, so the browser
gate can never pass by skipping. ``PXAPI_BROWSER_CHANNEL=chrome`` drives an installed Google
Chrome instead of Playwright's own Chromium. ``PXAPI_BROWSER_SCREENSHOTS=<dir>`` keeps the
screenshots each viewport test takes.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

if os.environ.get("PXAPI_BROWSER_TESTS") == "required":
    from playwright import sync_api
else:
    sync_api = pytest.importorskip(
        "playwright.sync_api", reason="the browser group is not installed (uv sync --group browser)"
    )

import uvicorn

from pxapi.adapters.inbound.workbench import create_workbench_app, read_archive
from pxapi.application.validate_analysis_run import CANONICAL_MEMBERS, RECEIPT_FILE, bundle_digest
from pxapi.domain.run_validation import receipt_rule_violations
from pxapi.ports.page_fetch import FetchFailureKind, PageFetchFailure
from tests.adapters.test_workbench import HOSTILE_TEXT, Acquisitions, hostile_page
from tests.application.test_acquire_selected_pages import (
    ORIGIN,
    PAGE_A,
    PAGE_B,
    FakeFetcher,
    response,
)
from tests.contracts.support import CONTRACTS

NORMAL = {"width": 1280, "height": 900}
NARROW = {"width": 375, "height": 812}


class Served:
    """One Workbench application behind a real uvicorn server on a free loopback port."""

    def __init__(self, acquisitions: Acquisitions) -> None:
        app = create_workbench_app(registry=CONTRACTS, acquisition=acquisitions)
        config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.acquisitions = acquisitions

    def __enter__(self) -> Served:
        self.thread.start()
        for _ in range(500):
            if self.server.started:
                break
            threading.Event().wait(0.01)
        assert self.server.started, "uvicorn did not start"
        port = self.server.servers[0].sockets[0].getsockname()[1]
        self.base = f"http://127.0.0.1:{port}"
        return self

    def __exit__(self, *exc: object) -> None:
        if self.acquisitions.gate is not None:
            self.acquisitions.gate.set()
        self.server.should_exit = True
        self.thread.join(timeout=10)


def deterministic_site() -> Acquisitions:
    """Four pages; page A carries hostile text, page B times out."""
    return Acquisitions(
        FakeFetcher(
            {
                PAGE_A: response(PAGE_A, body=hostile_page()),
                PAGE_B: PageFetchFailure(FetchFailureKind.TIMEOUT),
            }
        )
    )


@pytest.fixture(scope="module")
def browser() -> Iterator[Any]:
    channel = os.environ.get("PXAPI_BROWSER_CHANNEL") or None
    with sync_api.sync_playwright() as playwright:
        launched = playwright.chromium.launch(channel=channel, headless=True)
        yield launched
        launched.close()


@pytest.fixture
def served() -> Iterator[Served]:
    with Served(deterministic_site()) as running:
        yield running


@pytest.fixture
def dialogs() -> list[str]:
    return []


def open_page(browser: Any, viewport: dict[str, int], dialogs: list[str]) -> Any:
    context = browser.new_context(viewport=viewport, accept_downloads=True)
    page = context.new_page()
    page.on("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.dismiss()))
    return page


def screenshot(page: Any, name: str, tmp_path: Path) -> None:
    target = Path(os.environ.get("PXAPI_BROWSER_SCREENSHOTS") or tmp_path)
    target.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(target / f"{name}.png"), full_page=True)


def start_run(page: Any, base: str, url: str = ORIGIN, budget: str = "3") -> None:
    page.goto(f"{base}/operator")
    page.get_by_label("Target URL").fill(url)
    page.get_by_label("Maximum selected pages").fill(budget)
    page.get_by_role("button", name="Start analysis").click()
    page.wait_for_url(f"{base}/operator/runs/*")


def no_horizontal_scroll(page: Any) -> bool:
    return bool(
        page.evaluate(
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
        )
    )


# --- the journey --------------------------------------------------------------------------


def test_the_full_journey_from_url_to_downloaded_evidence(
    browser: Any, served: Served, dialogs: list[str], tmp_path: Path
) -> None:
    page = open_page(browser, NORMAL, dialogs)
    start_run(page, served.base)

    # Run overview, stages and validation, stated in words.
    assert page.get_by_role("heading", level=1).inner_text().startswith("Run ")
    overview = page.locator("#overview")
    assert ORIGIN in overview.inner_text()
    assert overview.locator(".badge.run-ok").inner_text().startswith("SUCCEEDED")
    assert "PAGE_ACQUISITION" in overview.inner_text()
    validation = page.locator("#validation")
    assert validation.locator(".overall .badge").inner_text().split(" \u2014 ")[0] == "! BLOCKED"
    gate_rows = validation.locator("table.gates tbody tr")
    assert gate_rows.count() == 7
    states = {
        gate_rows.nth(i).locator("code").first.inner_text(): gate_rows.nth(i)
        .locator(".badge")
        .inner_text()
        for i in range(7)
    }
    assert states["ACQUISITION_COMPLETENESS"] == "! BLOCKED"
    assert states["EVIDENCE_COVERAGE"] == "! BLOCKED"
    assert states["INPUT_CONTRACT"] == "\u2713 PASS"
    assert states["ARTIFACT_BUNDLE_VALIDITY"] == "\u2713 PASS"
    for gate in ("INPUT_CONTRACT", "ACQUISITION_COMPLETENESS", "EVIDENCE_COVERAGE"):
        assert gate in validation.inner_text()
    assert "SELECTION_INCOMPLETE" in validation.inner_text()
    assert "PAGE_NOT_ACQUIRED" in validation.inner_text()

    # Coverage and pages: the population, the budget-limited selection, per-page outcomes.
    coverage = page.locator("#coverage").inner_text()
    assert "Site inventory" in coverage and "Sampling manifest" in coverage
    assert "SELECTION_BUDGET_EXHAUSTED" in coverage
    pages = page.locator("#pages").inner_text()
    assert "Response received" in pages
    assert "Technical limitation: TIMEOUT" in pages

    # Evidence inspector: page -> measurement -> evidence, opened like a person would.
    details = page.locator("details.page-evidence")
    assert details.count() == 3
    hostile = details.nth(1)
    hostile.locator("summary").click()
    assert hostile.get_attribute("open") is not None
    table = hostile.locator("table")
    assert table.is_visible()
    assert HOSTILE_TEXT in table.inner_text(), "the hostile title is shown, as text"
    assert "Website evidence" in table.inner_text()
    timed_out = details.nth(2)
    timed_out.locator("summary").click()
    assert "Missing evidence" in timed_out.inner_text()
    assert "Technical limitation: TIMEOUT" in timed_out.inner_text()

    # Nothing the website wrote became markup, and nothing ran.
    assert page.locator("script").count() == 0
    assert page.locator("img").count() == 0
    assert dialogs == []

    # Artifact download and read-back, in the browser's own download.
    with page.expect_download() as download_info:
        page.get_by_role("link", name="Download the canonical artifact bundle (zip)").click()
    archive = tmp_path / "bundle.zip"
    download_info.value.save_as(str(archive))
    files = read_archive(archive.read_bytes())
    assert set(files) == {m.file_name for m in CANONICAL_MEMBERS.values()}
    for member in CANONICAL_MEMBERS.values():
        value = json.loads(files[member.file_name])
        for document in value if member.plural else [value]:
            assert CONTRACTS.validate(member.contract, document) == ()
    with page.expect_download() as receipt_info:
        page.get_by_role("link", name="Download the validation receipt").click()
    receipt_file = tmp_path / RECEIPT_FILE
    receipt_info.value.save_as(str(receipt_file))
    receipt = json.loads(receipt_file.read_bytes())
    assert CONTRACTS.validate("analysis-validation-receipt", receipt) == ()
    assert receipt_rule_violations(receipt) == ()
    assert receipt["overall_state"] == "BLOCKED"
    assert receipt["artifact_bundle_digest"] == bundle_digest(files)
    screenshot(page, "journey-normal-result", tmp_path)


def test_reload_and_back_never_submit_the_run_again(
    browser: Any, served: Served, dialogs: list[str]
) -> None:
    page = open_page(browser, NORMAL, dialogs)
    start_run(page, served.base)
    result_url = page.url
    before = page.locator("#overview").inner_text()

    page.reload()
    assert page.url == result_url
    assert page.locator("#overview").inner_text() == before
    page.go_back()
    assert page.url == f"{served.base}/operator"
    page.go_forward()
    assert page.url == result_url
    page.reload()
    assert len(served.acquisitions.budgets) == 1, "the run was started exactly once"
    assert dialogs == [], "no resubmission prompt: the result is a GET"


def test_a_second_submission_while_a_run_is_active_gets_the_409_guard(
    browser: Any, dialogs: list[str]
) -> None:
    acquisitions = deterministic_site()
    acquisitions.gate = threading.Event()
    with Served(acquisitions) as running:
        first = open_page(browser, NORMAL, dialogs)
        first.goto(f"{running.base}/operator")
        first.get_by_label("Target URL").fill(ORIGIN)
        first.get_by_label("Maximum selected pages").fill("3")
        first.get_by_role("button", name="Start analysis").click(no_wait_after=True)
        assert acquisitions.started.wait(timeout=15), "the first run never started"

        second = open_page(browser, NORMAL, dialogs)
        second.goto(f"{running.base}/operator")
        assert "A run is in progress" in second.locator("main").inner_text()
        second.get_by_label("Target URL").fill(ORIGIN)
        second.get_by_label("Maximum selected pages").fill("2")
        with second.expect_response(f"{running.base}/operator/runs") as answer:
            second.get_by_role("button", name="Start analysis").click()
        assert answer.value.status == 409
        assert "A run is already in progress" in second.locator("h1").inner_text()

        acquisitions.gate.set()
        first.wait_for_url(f"{running.base}/operator/runs/*", timeout=30_000)
        assert "Run overview" in first.locator("#overview").inner_text()
        assert len(acquisitions.budgets) == 1


def test_the_whole_journey_is_operable_by_keyboard_with_a_visible_focus(
    browser: Any, served: Served, dialogs: list[str]
) -> None:
    page = open_page(browser, NORMAL, dialogs)
    page.goto(f"{served.base}/operator")

    def tab_to(predicate: str, limit: int = 25) -> None:
        for _ in range(limit):
            page.keyboard.press("Tab")
            if page.evaluate(predicate):
                return
        raise AssertionError(f"focus never reached: {predicate}")

    def focus_ring() -> str:
        return str(page.evaluate("getComputedStyle(document.activeElement).outlineStyle"))

    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.textContent") == "Skip to main content"
    assert focus_ring() != "none"

    tab_to("document.activeElement.id === 'url'")
    assert focus_ring() != "none"
    page.keyboard.type(ORIGIN)
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.id") == "max_selected_pages"
    page.keyboard.type("3")
    tab_to("document.activeElement.tagName === 'BUTTON'")
    assert focus_ring() != "none"
    page.keyboard.press("Enter")
    page.wait_for_url(f"{served.base}/operator/runs/*")

    tab_to("document.activeElement.tagName === 'SUMMARY'", limit=80)
    assert focus_ring() != "none"
    page.keyboard.press("Enter")
    assert page.evaluate("document.activeElement.parentElement.open") is True
    tab_to("document.activeElement.textContent.startsWith('Download the canonical')", limit=400)
    assert focus_ring() != "none"


@pytest.mark.parametrize("viewport", [NORMAL, NARROW], ids=["normal", "narrow"])
def test_both_viewports_render_without_horizontal_page_scroll(
    browser: Any, served: Served, dialogs: list[str], viewport: dict[str, int], tmp_path: Path
) -> None:
    page = open_page(browser, viewport, dialogs)
    page.goto(f"{served.base}/operator")
    assert no_horizontal_scroll(page)
    label = "narrow" if viewport is NARROW else "normal"
    screenshot(page, f"start-{label}", tmp_path)

    start_run(page, served.base)
    for index in range(page.locator("details.page-evidence").count()):
        page.locator("details.page-evidence").nth(index).locator("summary").click()
    assert no_horizontal_scroll(page), "wide content scrolls inside its own container"
    assert page.get_by_role("main").is_visible()
    assert page.get_by_role("navigation", name="On this page").is_visible()
    screenshot(page, f"result-{label}", tmp_path)


def test_a_refused_input_is_announced_and_the_form_keeps_what_is_safe_to_keep(
    browser: Any, served: Served, dialogs: list[str]
) -> None:
    page = open_page(browser, NORMAL, dialogs)
    page.goto(f"{served.base}/operator")
    page.get_by_label("Target URL").fill("https://operator:s3cr3t@example.com/")
    page.get_by_label("Maximum selected pages").fill("3")
    page.get_by_role("button", name="Start analysis").click()
    alert = page.get_by_role("alert")
    assert "credentials" in alert.inner_text()
    assert "s3cr3t" not in page.content()
    assert page.get_by_label("Maximum selected pages").input_value() == "3"
    assert served.acquisitions.budgets == []
