"""The Operator Workbench adapter, over HTTP: input, one-run guard, result, downloads, safety.

Most runs here are produced by the real acquisition runtime over the fake ports of
``tests/application/test_acquire_selected_pages.py``, injected through the adapter's acquisition
factory — the only seam it has. The production wiring is exercised too: a loopback target is
refused by the shipped safety policy before any connection, so that test needs no network.
"""

from __future__ import annotations

import ast
import html.parser
import io
import itertools
import json
import re
import threading
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pxapi.adapters.composition import build_site_acquisition
from pxapi.adapters.inbound import workbench as workbench_module
from pxapi.adapters.inbound.http_api import create_app as create_http_api
from pxapi.adapters.inbound.workbench import (
    LOOPBACK_HOSTS,
    SECURITY_HEADERS,
    Workbench,
    archive_of,
    create_workbench_app,
    read_archive,
)
from pxapi.application.validate_analysis_run import (
    CANONICAL_MEMBERS,
    RECEIPT_CONTRACT,
    RECEIPT_FILE,
    bundle_digest,
)
from pxapi.domain.run_validation import receipt_rule_violations
from pxapi.domain.sampling_policy import SelectionBudgets
from pxapi.ports.page_fetch import FetchFailureKind, PageFetchFailure
from tests.application.test_acquire_selected_pages import (
    ORIGIN,
    PAGE_A,
    PAGE_B,
    FakeFetcher,
    build,
    response,
)
from tests.contracts.support import CONTRACTS

#: Site-controlled text that decodes to markup once the page's HTML is parsed.
HOSTILE_TITLE_HTML = "&lt;script&gt;alert(1)&lt;/script&gt; Kanzlei"
HOSTILE_TEXT = "<script>alert(1)</script>"
HOSTILE_DESCRIPTION_HTML = "&lt;img src=x onerror=alert(2)&gt; &quot;quoted&quot;"


def hostile_page() -> bytes:
    return (
        "<!doctype html><html><head>"
        f"<title>{HOSTILE_TITLE_HTML}</title>"
        f'<meta name="description" content="{HOSTILE_DESCRIPTION_HTML}">'
        "</head><body>x</body></html>"
    ).encode()


class Acquisitions:
    """An acquisition factory over fake ports that records every budget it was built for."""

    def __init__(self, fetcher: FakeFetcher | None = None, **build_kwargs: Any) -> None:
        self.fetcher = fetcher or FakeFetcher()
        self.build_kwargs = build_kwargs
        self.budgets: list[SelectionBudgets] = []
        self.gate: threading.Event | None = None
        self.started = threading.Event()

    def __call__(self, budgets: SelectionBudgets, registry: Any) -> Any:
        self.budgets.append(budgets)
        use = build(self.fetcher, budgets.max_selected_pages, **self.build_kwargs)
        factory = self

        class Gated:
            def run(self, request: dict[str, Any]) -> dict[str, Any]:
                factory.started.set()
                if factory.gate is not None:
                    assert factory.gate.wait(timeout=30), "the test never released the run"
                return use.run(request)

        return Gated()


#: The Host names a test application answers to: the test client's own, plus loopback.
TEST_HOSTS = ("testserver", *LOOPBACK_HOSTS)


def client_for(acquisitions: Any = None, **kwargs: Any) -> TestClient:
    app = create_workbench_app(
        registry=CONTRACTS,
        acquisition=acquisitions or Acquisitions(),
        allowed_hosts=TEST_HOSTS,
        **kwargs,
    )
    return TestClient(app)


def submit(client: TestClient, url: str = ORIGIN, budget: str = "3", **kwargs: Any) -> Any:
    return client.post(
        "/operator/runs",
        data={"url": url, "max_selected_pages": budget},
        follow_redirects=False,
        **kwargs,
    )


def completed_run(client: TestClient, url: str = ORIGIN, budget: str = "3") -> str:
    answer = submit(client, url, budget)
    assert answer.status_code == 303, answer.text
    return answer.headers["location"]


class Tags(html.parser.HTMLParser):
    """Every start tag and attribute name a browser would build from a document."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.attributes: list[str] = []
        self.text: list[str] = []
        self.ids: list[str] = []
        self.label_targets: list[str] = []
        self.inputs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        named = dict(attrs)
        self.attributes += [name for name, _ in attrs]
        if named.get("id"):
            self.ids.append(str(named["id"]))
        if tag == "label" and named.get("for"):
            self.label_targets.append(str(named["for"]))
        if tag == "input" and named.get("type") != "hidden":
            self.inputs.append(str(named.get("id")))

    def handle_data(self, data: str) -> None:
        self.text.append(data)


def parsed(document: str) -> Tags:
    tags = Tags()
    tags.feed(document)
    return tags


#: Attributes whose value a browser dereferences or navigates to.
URL_ATTRIBUTES = frozenset({"href", "src", "action", "formaction", "srcset", "data", "poster"})


def assert_inert(document: str) -> Tags:
    """No script element, no event-handler attribute, no URL attribute a script could hide in."""
    tags = parsed(document)
    assert "script" not in tags.tags
    assert [name for name in tags.attributes if name.lower().startswith("on")] == []
    for _tag, attrs in _anchor_attrs(document):
        for name, value in attrs:
            if name in URL_ATTRIBUTES:
                assert value.startswith(("#", "/operator")), (name, value)
    return tags


# --- the start page ------------------------------------------------------------------------


def test_the_start_page_asks_for_a_url_and_an_explicit_budget_with_no_default() -> None:
    page = client_for().get("/operator")
    assert page.status_code == 200
    tags = assert_inert(page.text)
    assert tags.inputs == ["url", "max_selected_pages"]
    assert sorted(tags.label_targets) == sorted(tags.inputs), "every input has a real label"
    assert 'name="max_selected_pages"' in page.text
    assert 'value=""' in page.text.split('id="max_selected_pages"')[1].split(">")[0], (
        "the budget field must start empty: there is no default"
    )


def test_the_start_page_has_landmarks_and_one_top_heading() -> None:
    tags = parsed(client_for().get("/operator").text)
    for landmark in ("header", "main", "footer"):
        assert landmark in tags.tags
    assert tags.tags.count("h1") == 1
    assert "button" in tags.tags


# --- input -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "budget"),
    [("", "3"), (ORIGIN, ""), ("", "")],
    ids=["url-missing", "budget-missing", "both-missing"],
)
def test_a_missing_url_or_budget_is_refused_and_nothing_runs(url: str, budget: str) -> None:
    acquisitions = Acquisitions()
    answer = submit(client_for(acquisitions), url, budget)
    assert answer.status_code == 422
    assert acquisitions.budgets == []
    assert 'role="alert"' in answer.text


def test_a_form_without_the_budget_field_at_all_is_refused() -> None:
    acquisitions = Acquisitions()
    answer = client_for(acquisitions).post(
        "/operator/runs", data={"url": ORIGIN}, follow_redirects=False
    )
    assert answer.status_code == 422
    assert "there is no default" in answer.text
    assert acquisitions.budgets == []


@pytest.mark.parametrize("budget", ["0", "-1", "abc", "1.5", " 3", "٣", "+3", "9" * 5000])
def test_a_budget_that_is_not_a_whole_number_of_at_least_one_is_refused(budget: str) -> None:
    acquisitions = Acquisitions()
    answer = submit(client_for(acquisitions), ORIGIN, budget)
    assert answer.status_code == 422
    assert acquisitions.budgets == []


@pytest.mark.parametrize(
    "url",
    ["not a url", "ftp://example.com/", "https://", "//example.com/", "example.com"],
)
def test_an_invalid_url_is_refused_by_the_request_contract(url: str) -> None:
    acquisitions = Acquisitions()
    answer = submit(client_for(acquisitions), url)
    assert answer.status_code == 422
    assert "absolute public http(s) URL" in answer.text
    assert acquisitions.budgets == []


def test_a_credential_bearing_url_is_refused_without_being_echoed() -> None:
    acquisitions = Acquisitions()
    answer = submit(client_for(acquisitions), "https://operator:s3cr3t-token@example.com/")
    assert answer.status_code == 422
    assert "s3cr3t-token" not in answer.text
    assert "operator:" not in answer.text
    assert acquisitions.budgets == []


def test_duplicated_fields_are_not_a_valid_form() -> None:
    acquisitions = Acquisitions()
    answer = client_for(acquisitions).post(
        "/operator/runs",
        content=b"url=https%3A%2F%2Fexample.com%2F&url=https%3A%2F%2Fother.test%2F"
        b"&max_selected_pages=3",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    assert answer.status_code == 422
    assert acquisitions.budgets == []


def test_the_declared_budget_becomes_the_manifest_s_selection_budget() -> None:
    acquisitions = Acquisitions()
    client = client_for(acquisitions)
    location = completed_run(client, budget="2")
    assert acquisitions.budgets == [SelectionBudgets(max_selected_pages=2)]
    receipt = client.get(f"{location}/{RECEIPT_FILE}").json()
    assert receipt["gates"]["INPUT_CONTRACT"]["state"] == "PASS"
    assert "SELECTION_INCOMPLETE" in json.dumps(receipt)


# --- safety ------------------------------------------------------------------------------------


def test_a_private_target_is_refused_by_the_shipped_policy_and_shown_neutrally() -> None:
    """Production wiring: the loopback target is refused before any connection is opened."""
    client = TestClient(create_workbench_app(registry=CONTRACTS, allowed_hosts=TEST_HOSTS))
    location = completed_run(client, "http://127.0.0.1:9/", "3")
    page = client.get(location)
    assert page.status_code == 200
    assert "TARGET_NOT_PERMITTED" in page.text
    assert "RUN_FAILED_TECHNICALLY" in page.text
    receipt = client.get(f"{location}/{RECEIPT_FILE}").json()
    assert receipt["run_state"] == "FAILED"
    assert receipt["overall_state"] == "BLOCKED"


def test_the_production_workbench_drives_the_shared_multi_page_composition() -> None:
    """No second pipeline: production passes ``build_site_acquisition`` itself."""
    app = create_workbench_app(registry=CONTRACTS)
    workbench: Workbench = app.state.workbench
    assert workbench.acquisition is build_site_acquisition


def test_the_workbench_imports_no_discovery_fetch_or_observation_machinery() -> None:
    """The adapter reaches the analysis only through the composition root."""
    source = Path(workbench_module.__file__).read_text(encoding="utf-8")
    imported = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module
    }
    forbidden = {
        "pxapi.adapters.web.page_fetcher",
        "pxapi.adapters.web.site_discovery",
        "pxapi.adapters.web.html_observations",
        "pxapi.application.discover_site",
        "pxapi.application.observe_static_page",
        "pxapi.application.acquire_selected_pages",
        "subprocess",
    }
    imported_modules = {
        alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert imported & forbidden == set()
    assert not {"subprocess", "multiprocessing", "os"} & imported_modules


def test_a_cross_site_form_post_is_refused_and_nothing_runs() -> None:
    acquisitions = Acquisitions()
    answer = submit(client_for(acquisitions), headers={"Origin": "https://attacker.example"})
    assert answer.status_code == 403
    assert acquisitions.budgets == []


def test_a_same_origin_form_post_is_accepted() -> None:
    answer = submit(client_for(), headers={"Origin": "http://testserver"})
    assert answer.status_code == 303


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        # What Chrome actually sends for our own form under Referrer-Policy: no-referrer:
        # measured with Playwright on Chrome 154 — the origin is serialised as "null".
        ({"Origin": "null", "Sec-Fetch-Site": "same-origin"}, 303),
        ({"Sec-Fetch-Site": "same-origin"}, 303),
        ({"Origin": "http://testserver", "Sec-Fetch-Site": "cross-site"}, 403),
        ({"Origin": "null", "Sec-Fetch-Site": "same-site"}, 403),
        ({"Origin": "null"}, 403),
        ({"Sec-Fetch-Site": "cross-site"}, 403),
    ],
    ids=[
        "null-origin-same-origin",
        "fetch-metadata-only",
        "cross-site-despite-origin",
        "same-site-is-not-same-origin",
        "null-origin-without-metadata",
        "cross-site-only",
    ],
)
def test_the_origin_check_trusts_the_browser_s_fetch_metadata(
    headers: dict[str, str], status: int
) -> None:
    assert submit(client_for(), headers=headers).status_code == status


def test_a_submission_that_is_not_a_form_is_refused() -> None:
    answer = client_for().post(
        "/operator/runs", json={"url": ORIGIN, "max_selected_pages": 3}, follow_redirects=False
    )
    assert answer.status_code == 415


def test_an_oversized_submission_is_refused() -> None:
    answer = client_for().post(
        "/operator/runs",
        content=b"url=" + b"a" * 20_000 + b"&max_selected_pages=3",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    assert answer.status_code == 413


@pytest.mark.parametrize("path", ["/operator", "/operator/runs/unknown", "/operator/workbench.css"])
def test_every_response_carries_the_security_headers(path: str) -> None:
    answer = client_for().get(path)
    for name, value in SECURITY_HEADERS.items():
        assert answer.headers[name] == value
    assert "script-src" not in SECURITY_HEADERS["Content-Security-Policy"]
    assert "default-src 'none'" in SECURITY_HEADERS["Content-Security-Policy"]


def test_the_workbench_exposes_no_machine_api_and_the_homepage_api_no_workbench() -> None:
    workbench_paths = {route.path for route in create_workbench_app(registry=CONTRACTS).routes}
    assert not any(path.startswith("/v1") for path in workbench_paths)
    assert not {"/openapi.json", "/docs", "/redoc"} & workbench_paths
    api_paths = {route.path for route in create_http_api(registry=CONTRACTS).routes}
    assert not any(path.startswith("/operator") for path in api_paths)
    assert "/v1/analysis-runs" in api_paths


# --- escaping: website text is only ever text ------------------------------------------------


def test_website_text_carrying_markup_renders_only_as_text() -> None:
    fetcher = FakeFetcher({PAGE_A: response(PAGE_A, body=hostile_page())})
    client = client_for(Acquisitions(fetcher))
    page = client.get(completed_run(client, budget="4"))
    assert page.status_code == 200
    tags = assert_inert(page.text)
    visible = "".join(tags.text)
    assert HOSTILE_TEXT in visible, "canary: the hostile title must reach the page as text"
    assert '<img src=x onerror=alert(2)> "quoted"' in visible
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page.text
    assert "img" not in tags.tags


def test_a_hostile_target_url_is_escaped_on_the_result_and_the_form() -> None:
    hostile = 'https://example.com/?q="><script>alert(3)</script>'
    client = client_for()
    page = client.get(completed_run(client, hostile))
    assert_inert(page.text)
    assert "alert(3)" in "".join(parsed(page.text).text)
    refused = submit(client, 'javascript:alert(4)//"><script>alert(5)</script>')
    assert refused.status_code == 422
    assert_inert(refused.text)


def test_no_website_url_is_ever_rendered_as_a_link() -> None:
    client = client_for()
    page = client.get(completed_run(client, budget="4"))
    hrefs = [
        value
        for tag, attrs in _anchor_attrs(page.text)
        for name, value in attrs
        if tag == "a" and name == "href"
    ]
    assert hrefs, "canary: the page has links of its own"
    assert all(href.startswith(("#", "/operator")) for href in hrefs), hrefs


def _anchor_attrs(document: str) -> list[tuple[str, list[tuple[str, str]]]]:
    found: list[tuple[str, list[tuple[str, str]]]] = []

    class Anchors(html.parser.HTMLParser):
        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            found.append((tag, [(k, v or "") for k, v in attrs]))

    Anchors().feed(document)
    return found


# --- the result -----------------------------------------------------------------------------


def test_the_result_page_shows_every_required_part_of_the_run() -> None:
    fetcher = FakeFetcher({PAGE_B: PageFetchFailure(FetchFailureKind.TIMEOUT)})
    client = client_for(Acquisitions(fetcher))
    location = completed_run(client, budget="3")
    run_id = location.rsplit("/", 1)[1]
    page = client.get(location)
    assert page.status_code == 200
    tags = assert_inert(page.text)
    text = " ".join(tags.text)
    for anchor in ("overview", "validation", "limitations", "coverage", "pages", "evidence"):
        assert anchor in tags.ids, anchor
    assert "artifacts" in tags.ids
    for expected in (
        ORIGIN,
        run_id,
        "SUCCEEDED",
        "DISCOVERY",
        "PAGE_ACQUISITION",
        "Declared page budget",
        "Site inventory",
        "Sampling manifest",
        "selection_complete",
        "SELECTION_BUDGET_EXHAUSTED",
        "Technical limitation: TIMEOUT",
        "Missing evidence",
        "Website evidence",
        "HTTP_STATUS",
        "PAGE_TITLE",
        "BLOCKED",
        "ACQUISITION_COMPLETENESS",
        "PAGE_NOT_ACQUIRED",
        "SELECTION_INCOMPLETE",
        "Download the canonical artifact bundle",
        "Download the validation receipt",
    ):
        assert expected in text, expected
    assert "details" in tags.tags and "summary" in tags.tags


def test_headings_never_skip_a_level() -> None:
    client = client_for()
    tags = parsed(client.get(completed_run(client)).text)
    levels = [int(tag[1]) for tag in tags.tags if tag in {"h1", "h2", "h3", "h4"}]
    assert levels[0] == 1 and levels.count(1) == 1
    assert all(b - a <= 1 for a, b in itertools.pairwise(levels)), levels


def test_every_state_is_stated_in_words_not_only_by_colour() -> None:
    client = client_for(
        Acquisitions(FakeFetcher({PAGE_B: PageFetchFailure(FetchFailureKind.TIMEOUT)}))
    )
    page = client.get(completed_run(client))
    for word in ("PASS", "BLOCKED", "Technical limitation", "Missing evidence", "Website evidence"):
        assert word in page.text


def test_reloading_the_result_is_safe_and_starts_nothing() -> None:
    acquisitions = Acquisitions()
    client = client_for(acquisitions)
    location = completed_run(client)
    first = client.get(location)
    second = client.get(location)
    assert first.status_code == second.status_code == 200
    assert first.text == second.text
    assert len(acquisitions.budgets) == 1


def test_a_run_nobody_kept_is_not_available() -> None:
    client = client_for()
    assert client.get("/operator/runs/px-00000000000000000000000000000000").status_code == 404
    assert client.get("/operator/runs/..%2Fetc").status_code == 404
    assert client.get("/operator/runs/nope/artifacts.zip").status_code == 404


def test_only_the_most_recent_run_is_kept() -> None:
    client = client_for()
    first = completed_run(client)
    second = completed_run(client)
    assert client.get(first).status_code == 404
    assert client.get(second).status_code == 200
    start = client.get("/operator").text
    assert second.rsplit("/", 1)[1] in start


def test_state_does_not_survive_a_new_process() -> None:
    """Ephemeral V1: a fresh application (a restart) knows no earlier run."""
    acquisitions = Acquisitions()
    location = completed_run(client_for(acquisitions))
    assert client_for(acquisitions).get(location).status_code == 404


# --- one run at a time ----------------------------------------------------------------------


def test_a_second_submission_while_a_run_is_active_is_refused_with_409() -> None:
    acquisitions = Acquisitions()
    acquisitions.gate = threading.Event()
    client = client_for(acquisitions)
    first: dict[str, Any] = {}

    def run_first() -> None:
        first["answer"] = submit(client)

    worker = threading.Thread(target=run_first)
    worker.start()
    try:
        assert acquisitions.started.wait(timeout=10), "the first run never started"
        second = submit(client)
        assert second.status_code == 409
        assert "already in progress" in second.text
        assert len(acquisitions.budgets) == 1, "the second submission must not build a run"
        start = client.get("/operator").text
        assert "A run is in progress" in start
    finally:
        acquisitions.gate.set()
        worker.join(timeout=30)
    assert first["answer"].status_code == 303
    third = submit(client)
    assert third.status_code == 303, "the guard is released once the run has finished"


def test_an_internal_defect_during_a_run_is_reported_and_releases_the_slot() -> None:
    class Exploding:
        calls = 0

        def __call__(self, budgets: SelectionBudgets, registry: Any) -> Any:
            Exploding.calls += 1
            if Exploding.calls == 1:
                raise RuntimeError("boom-internal-7f3 /secret/path")
            return build(FakeFetcher(), budgets.max_selected_pages)

    client = client_for(Exploding())
    failed = submit(client)
    assert failed.status_code == 500
    assert "Nothing about the website is implied" in failed.text
    assert "boom-internal-7f3" not in failed.text
    assert "/secret/path" not in failed.text
    assert submit(client).status_code == 303


# --- canonical output defects are withheld --------------------------------------------------


def test_a_run_whose_documents_break_their_contract_is_withheld_but_its_receipt_explains() -> None:
    def break_contract(envelope: dict[str, Any]) -> None:
        envelope["measurements"][0]["schema_version"] = "9.9.9"

    class Tampering(Acquisitions):
        def __call__(self, budgets: SelectionBudgets, registry: Any) -> Any:
            inner = super().__call__(budgets, registry)

            class Tampered:
                def run(self, request: dict[str, Any]) -> dict[str, Any]:
                    envelope = inner.run(request)
                    break_contract(envelope)
                    return envelope

            return Tampered()

    client = client_for(Tampering())
    location = completed_run(client, budget="4")
    page = client.get(location)
    assert page.status_code == 500
    assert "Canonical documents withheld" in page.text
    assert "measurement-record" in page.text
    assert client.get(f"{location}/artifacts.zip").status_code == 404
    receipt = client.get(f"{location}/{RECEIPT_FILE}").json()
    assert receipt["overall_state"] == "FAIL"
    assert receipt["gates"]["CANONICAL_VALIDITY"]["state"] == "FAIL"


# --- downloads --------------------------------------------------------------------------------


def test_the_artifact_bundle_downloads_and_reads_back_as_valid_canonical_documents() -> None:
    client = client_for()
    location = completed_run(client, budget="4")
    download = client.get(f"{location}/artifacts.zip")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    assert "attachment" in download.headers["content-disposition"]
    files = read_archive(download.content)
    canonical = {member.file_name for member in CANONICAL_MEMBERS.values()}
    assert set(files) == canonical, "the bundle is the canonical documents and nothing else"

    for member in CANONICAL_MEMBERS.values():
        value = json.loads(files[member.file_name])
        documents = value if member.plural else [value]
        for document in documents:
            assert CONTRACTS.validate(member.contract, document) == (), member.file_name

    receipt = client.get(f"{location}/{RECEIPT_FILE}").json()
    assert CONTRACTS.validate(RECEIPT_CONTRACT, receipt) == ()
    assert receipt_rule_violations(receipt) == ()
    assert receipt["overall_state"] == "PASS"
    assert receipt["artifact_bundle_digest"] == bundle_digest(files)


def test_the_bundle_is_deterministic_across_downloads() -> None:
    client = client_for()
    location = completed_run(client)
    assert client.get(f"{location}/artifacts.zip").content == (
        client.get(f"{location}/artifacts.zip").content
    )


def test_the_receipt_downloads_on_its_own_and_pins_the_bundle_it_validated() -> None:
    client = client_for()
    location = completed_run(client)
    alone = client.get(f"{location}/{RECEIPT_FILE}")
    assert alone.status_code == 200
    assert alone.headers["content-type"] == "application/json"
    assert "attachment" in alone.headers["content-disposition"]
    bundle = read_archive(client.get(f"{location}/artifacts.zip").content)
    assert alone.json()["artifact_bundle_digest"] == bundle_digest(bundle)


def test_the_archive_helpers_round_trip_exactly() -> None:
    files = {"b.json": b"{}\n", "a.json": b"[1]\n"}
    content = archive_of(files)
    assert read_archive(content) == files
    assert archive_of(dict(reversed(list(files.items())))) == content
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert [info.filename for info in archive.infolist()] == ["a.json", "b.json"]


def test_the_stylesheet_is_local_and_references_nothing_remote() -> None:
    css = client_for().get("/operator/workbench.css")
    assert css.status_code == 200
    assert css.headers["content-type"].startswith("text/css")
    assert "url(" not in css.text and "@import" not in css.text
    assert ":focus-visible" in css.text


# --- independent review findings (2026-09-29) ----------------------------------------------

SECRET = "s3cr3t-token"


@pytest.mark.parametrize(
    "url",
    [
        f"https://operator:{SECRET}@example.com/a\\b",
        f"https://operator:{SECRET}@example.com/a{chr(0xA0)}b",
        f"https://operator:{SECRET}@example.com/a{chr(0x3000)}b",
        f"https://operator:{SECRET}@exa[mple.com/",
        f"https://operator:{SECRET}@[::1/",
        f"https://operator:{SECRET}@example.com/a b",
        f"ftp://operator:{SECRET}@example.com/",
        f"https://operator:{SECRET}@example.com/" + "a" * 2100,
        f"https:\\\\operator:{SECRET}@example.com/",
    ],
    ids=[
        "backslash",
        "nbsp",
        "ideographic-space",
        "bracket",
        "ipv6-bracket",
        "space",
        "ftp",
        "over-length",
        "backslash-scheme",
    ],
)
def test_a_credential_url_with_a_second_defect_is_refused_and_never_echoed(url: str) -> None:
    """Userinfo is detected whatever other rule the URL breaks first."""
    acquisitions = Acquisitions()
    answer = submit(client_for(acquisitions), url)
    assert answer.status_code == 422
    assert SECRET not in answer.text
    assert acquisitions.budgets == []


def test_the_served_bundle_is_exactly_the_validated_canonical_bundle() -> None:
    """No circularity in what is downloaded: the zip holds the canonical documents only, and
    re-validating it with the shipped use case reproduces the receipt's bundle verdict."""
    from pxapi.application.validate_analysis_run import ValidateAnalysisRun

    client = client_for()
    location = completed_run(client, budget="4")
    files = read_archive(client.get(f"{location}/artifacts.zip").content)
    receipt = client.get(f"{location}/{RECEIPT_FILE}").json()
    assert RECEIPT_FILE not in files
    assert set(files) == {member.file_name for member in CANONICAL_MEMBERS.values()}
    assert bundle_digest(files) == receipt["artifact_bundle_digest"]
    envelope = {
        name: json.loads(files[member.file_name]) for name, member in CANONICAL_MEMBERS.items()
    }
    again = ValidateAnalysisRun(CONTRACTS, lambda: __import__("datetime").datetime.now(), str).run(
        envelope, files, run_id=receipt["run_id"], declared_budget=4
    )
    assert again["gates"]["ARTIFACT_BUNDLE_VALIDITY"] == {"state": "PASS", "reasons": []}
    assert again["overall_state"] == receipt["overall_state"]


def _anchors_resolve(document: str) -> list[str]:
    tags = parsed(document)
    targets = [
        value[1:]
        for _tag, attrs in _anchor_attrs(document)
        for name, value in attrs
        if name == "href" and value.startswith("#")
    ]
    return [target for target in targets if target not in tags.ids]


def test_every_in_page_link_resolves_on_the_result_and_the_withheld_page() -> None:
    client = client_for()
    assert _anchors_resolve(client.get(completed_run(client)).text) == []

    def break_contract(envelope: dict[str, Any]) -> None:
        envelope["measurements"][0]["schema_version"] = "9.9.9"

    class Tampering(Acquisitions):
        def __call__(self, budgets: SelectionBudgets, registry: Any) -> Any:
            inner = super().__call__(budgets, registry)

            class Tampered:
                def run(self, request: dict[str, Any]) -> dict[str, Any]:
                    envelope = inner.run(request)
                    break_contract(envelope)
                    return envelope

            return Tampered()

    withheld_client = client_for(Tampering())
    page = withheld_client.get(completed_run(withheld_client)).text
    assert "Canonical documents withheld" in page
    assert _anchors_resolve(page) == []
    assert 'href="#withheld"' in page


@pytest.mark.parametrize("host", ["attacker.example:8000", "rebound.test", "10.0.0.5:8001"])
def test_a_foreign_host_is_refused_before_anything_runs(host: str) -> None:
    """DNS rebinding: the page is same-origin with the attacker's name, so only Host tells."""
    acquisitions = Acquisitions()
    client = client_for(acquisitions)
    headers = {"Host": host, "Sec-Fetch-Site": "same-origin", "Origin": f"http://{host}"}
    assert submit(client, headers=headers).status_code == 400
    assert client.get("/operator", headers={"Host": host}).status_code == 400
    assert acquisitions.budgets == []


def test_the_production_app_accepts_only_loopback_host_names() -> None:
    client = TestClient(create_workbench_app(registry=CONTRACTS))
    assert client.get("/operator").status_code == 400, "TestClient's own host is not loopback"
    assert client.get("/operator", headers={"Host": "127.0.0.1:8001"}).status_code == 200
    assert client.get("/operator", headers={"Host": "localhost:8001"}).status_code == 200


def _raw_post(app: Any, chunks: list[bytes], headers: list[tuple[bytes, bytes]]) -> tuple[int, int]:
    """Drive the ASGI app directly; return (status, how many body chunks it pulled)."""
    import asyncio

    pulled = 0
    status: list[int] = []
    queue = list(chunks)

    async def receive() -> dict[str, Any]:
        nonlocal pulled
        if queue:
            pulled += 1
            chunk = queue.pop(0)
            return {"type": "http.request", "body": chunk, "more_body": bool(queue)}
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            status.append(message["status"])

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/operator/runs",
        "raw_path": b"/operator/runs",
        "query_string": b"",
        "headers": [(b"host", b"testserver"), *headers],
        "client": ("127.0.0.1", 1),
        "server": ("testserver", 80),
    }
    asyncio.run(app(scope, receive, send))
    return status[0], pulled


def test_an_oversized_body_is_refused_without_being_buffered() -> None:
    app = create_workbench_app(
        registry=CONTRACTS, acquisition=Acquisitions(), allowed_hosts=("testserver",)
    )
    form = [(b"content-type", b"application/x-www-form-urlencoded")]
    chunk = b"a" * 1024
    status, pulled = _raw_post(app, [chunk] * 256, form)
    assert status == 413
    assert pulled <= 17, f"the app read {pulled} KiB before refusing"
    declared = [*form, (b"content-length", str(256 * 1024).encode())]
    status, pulled = _raw_post(app, [chunk] * 256, declared)
    assert status == 413
    assert pulled == 0, "a declared oversized body is refused before it is read"


# --- states are rendered as words on the elements that carry them ---------------------------


def _gate_rows(document: str) -> dict[str, str]:
    """``gate family -> the state word its row's badge renders``, read from the gates table."""
    rows: dict[str, str] = {}

    class Rows(html.parser.HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.in_gates = False
            self.row: list[str] = []
            self.cell = -1
            self.badge_depth = 0
            self.texts: list[list[str]] = []

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            classes = dict(attrs).get("class") or ""
            if tag == "table" and "gates" in classes.split():
                self.in_gates = True
            elif self.in_gates and tag == "tr":
                self.texts = []
            elif self.in_gates and tag == "td":
                self.texts.append([])

        def handle_endtag(self, tag: str) -> None:
            if tag == "table":
                self.in_gates = False
            elif self.in_gates and tag == "tr" and len(self.texts) == 3:
                family = re.findall(r"[A-Z][A-Z_]+", "".join(self.texts[0]))[-1]
                rows[family] = " ".join("".join(self.texts[1]).split())

        def handle_data(self, data: str) -> None:
            if self.in_gates and self.texts:
                self.texts[-1].append(data)

    Rows().feed(document)
    return rows


def test_each_gate_row_renders_the_receipt_s_own_state_in_words() -> None:
    fetcher = FakeFetcher({PAGE_B: PageFetchFailure(FetchFailureKind.TIMEOUT)})
    client = client_for(Acquisitions(fetcher))
    location = completed_run(client)
    receipt = client.get(f"{location}/{RECEIPT_FILE}").json()
    rows = _gate_rows(client.get(location).text)
    assert set(rows) == set(receipt["gates"])
    words = {
        "PASS": "PASS",
        "FAIL": "FAIL",
        "BLOCKED": "BLOCKED",
        "NOT_APPLICABLE": "NOT APPLICABLE",
    }
    for family, gate in receipt["gates"].items():
        assert rows[family].endswith(words[gate["state"]]), (family, rows[family])
    assert {rows["ACQUISITION_COMPLETENESS"], rows["INPUT_CONTRACT"]} == {"! BLOCKED", "✓ PASS"}


def test_the_overall_badge_and_the_run_state_render_the_real_states() -> None:
    fetcher = FakeFetcher({PAGE_B: PageFetchFailure(FetchFailureKind.TIMEOUT)})
    client = client_for(Acquisitions(fetcher))
    page = client.get(completed_run(client)).text
    overall = page.split('class="overall"')[1].split("</p>")[0]
    assert 'class="badge badge-blocked"' in overall
    assert "BLOCKED" in "".join(parsed(overall).text)
    run_state = page.split("<dt>Run state</dt>")[1].split("</dd>")[0]
    assert "SUCCEEDED" in "".join(parsed(run_state).text)
