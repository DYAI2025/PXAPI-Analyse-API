"""The Workbench views escape by construction, whatever a document carries.

The HTTP tests prove the realistic vectors (a page title, a meta description, a target URL).
This module proves the structural claim behind them: *every* string in a run — identifiers,
tokens and timestamps included, which a validated document could never carry this way — is
replaced in turn by a payload, and the rendered page still contains no element and no attribute
the payload did not come from.
"""

from __future__ import annotations

import ast
import copy
import html.parser
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from pxapi.adapters.inbound import workbench_views as views
from pxapi.application.validate_analysis_run import build_artifact_bundle
from pxapi.domain.run_validation import GateFamily
from pxapi.ports.page_fetch import FetchFailureKind, PageFetchFailure
from tests.application.run_fixtures import acquired, validate
from tests.application.test_acquire_selected_pages import PAGE_B, FakeFetcher

PAYLOAD = '"><script>alert(9)</script><img src=x onerror=alert(8)>'


class Elements(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.attributes: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        self.attributes += [name for name, _ in attrs]


def elements(document: str) -> Elements:
    parser = Elements()
    parser.feed(document)
    return parser


def string_paths(value: Any, path: tuple[Any, ...] = ()) -> Iterator[tuple[Any, ...]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield from string_paths(item, (*path, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from string_paths(item, (*path, index))
    elif isinstance(value, str):
        yield path


def with_payload(document: Any, path: tuple[Any, ...]) -> Any:
    changed = copy.deepcopy(document)
    target = changed
    for step in path[:-1]:
        target = target[step]
    target[path[-1]] = PAYLOAD
    return changed


def rendered(
    envelope: dict[str, Any], receipt: dict[str, Any], url: str = "https://x.test/"
) -> str:
    return views.result_page(
        views.ResultView(
            run_id="px-1",
            target_url=url,
            declared_budget=3,
            envelope=envelope,
            receipt=receipt,
            withheld_contracts=(),
            archive_available=True,
        )
    )


@pytest.fixture(scope="module")
def run() -> tuple[dict[str, Any], dict[str, Any]]:
    envelope = acquired(FakeFetcher({PAGE_B: PageFetchFailure(FetchFailureKind.TIMEOUT)}), budget=3)
    return envelope, validate(envelope, build_artifact_bundle(envelope), budget=3)


def baseline(run: tuple[dict[str, Any], dict[str, Any]]) -> Elements:
    return elements(rendered(*run))


def test_every_envelope_string_renders_as_text(run: tuple[dict[str, Any], dict[str, Any]]) -> None:
    envelope, receipt = run
    expected = baseline(run)
    paths = list(string_paths(envelope))
    assert len(paths) > 200, "canary: the sweep must cover the whole run"
    for path in paths:
        page = elements(rendered(with_payload(envelope, path), receipt))
        assert "script" not in page.tags, path
        assert "img" not in page.tags, path
        assert "onerror" not in page.attributes, path
        assert set(page.tags) <= set(expected.tags) | {"code", "span", "li", "ul"}, path


def test_every_receipt_string_renders_as_text(run: tuple[dict[str, Any], dict[str, Any]]) -> None:
    envelope, receipt = run
    for path in string_paths(receipt):
        page = elements(rendered(envelope, with_payload(receipt, path)))
        assert "script" not in page.tags, path
        assert "onerror" not in page.attributes, path


def test_the_target_url_and_form_echo_render_as_text() -> None:
    page = elements(
        views.start_page(views.FormState(url=PAYLOAD, budget=PAYLOAD, errors=(PAYLOAD,)))
    )
    assert "script" not in page.tags and "img" not in page.tags
    envelope = acquired(budget=2)
    result = elements(rendered(envelope, validate(envelope, budget=2), url=PAYLOAD))
    assert "script" not in result.tags


def test_the_payload_sweep_would_see_an_unescaped_value() -> None:
    """Canary: the parser really does report a payload that reached the page as markup."""
    assert "script" in elements(f"<p>{PAYLOAD}</p>").tags
    assert "onerror" in elements(f"<p>{PAYLOAD}</p>").attributes


def test_el_escapes_children_and_attributes_and_passes_its_own_markup_through() -> None:
    built = views.el("p", PAYLOAD, views.el("b", "ok"), title=PAYLOAD, class_="c")
    assert "<script>" not in built
    assert "&lt;script&gt;" in built
    assert 'title="&quot;&gt;&lt;script&gt;' in built
    assert "<b>ok</b>" in built
    assert views.void("input", value=PAYLOAD).count('"') == 2


def test_only_the_element_builders_construct_markup() -> None:
    """``Markup(...)`` is the one way to mark a string safe; only the builders may call it."""
    source = Path(views.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    callers = set()
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef):
            continue
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "Markup"
            ):
                callers.add(function.name)
    assert callers == {"el", "void", "page"}


def test_no_view_emits_a_script_element_or_an_inline_handler() -> None:
    source = Path(views.__file__).read_text(encoding="utf-8")
    assert 'el("script"' not in source and 'void("script"' not in source
    assert "on_click" not in source and "onclick" not in source.lower()


@pytest.mark.parametrize(
    ("assessment", "kind"),
    [
        ({"collection_mode": "OBSERVED", "result_state": "KNOWN"}, "evidence"),
        ({"collection_mode": "OBSERVED", "result_state": "UNKNOWN"}, "missing"),
        ({"not_assessed_reason": "TIMEOUT"}, "missing"),
        ({"not_assessed_reason": "UNSUPPORTED"}, "missing"),
        ({"collection_mode": "OBSERVED", "result_state": "NOT_APPLICABLE"}, "not-applicable"),
        ({"collection_mode": "OBSERVED", "result_state": "CONFLICT"}, "conflict"),
        (None, "missing"),
    ],
)
def test_an_assessment_is_described_in_words(assessment: Any, kind: str) -> None:
    described = views.describe_assessment(assessment)
    assert described.kind == kind
    assert described.label.strip()


def test_missing_evidence_is_never_described_as_negative() -> None:
    label = views.describe_assessment({"not_assessed_reason": "TIMEOUT"}).label
    assert "not a finding about the website" in label
    for word in ("fail", "bad", "poor", "missing on the page", "absent"):
        assert word not in label.lower()


def test_an_observed_false_is_website_evidence_shown_as_no() -> None:
    measurement = {
        "assessment": {"collection_mode": "OBSERVED", "result_state": "KNOWN"},
        "result": {"value_type": "BOOLEAN", "boolean_value": False},
    }
    assert views.describe_assessment(measurement["assessment"]).kind == "evidence"
    assert views.describe_value(measurement) == "no"


def test_every_gate_family_and_state_has_a_human_label() -> None:
    assert set(views.GATE_TITLES) == set(GateFamily)
    assert set(views.STATE_LABELS) == {"PASS", "FAIL", "BLOCKED", "NOT_APPLICABLE"}
    for symbol, word, explanation in views.STATE_LABELS.values():
        assert word and explanation and symbol
