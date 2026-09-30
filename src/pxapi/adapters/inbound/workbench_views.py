"""The Operator Workbench's HTML: semantic markup, one stylesheet, and no script at all.

Everything a website wrote is untrusted data, and this module is where it meets a browser. The
rule that keeps it text is **structural, not remembered**: markup is only ever built by
:func:`el` and :func:`void`, which escape every child and every attribute value that is not
already a :class:`Markup` built by them. A value read from a canonical document — a title, a
URL, a meta description, an identifier — can therefore only ever reach the page as escaped
text; there is no call in this module that inserts a caller's string as markup, and no website
URL is ever rendered as a link. The pages carry no JavaScript, and the adapter serves them
under a Content-Security-Policy that forbids script entirely, so even a defect here could not
execute anything.

The views read canonical documents only after they have satisfied their contracts, and show
nothing else: no raw response body, no header, no validator message.

Four kinds of statement are kept apart in text, never by colour alone: **website evidence**
(an assessment that established a value), **missing evidence** (not assessed, or unknown — a
limitation of this analysis), **not applicable**, and **technical limitation** (an acquisition
that did not complete). An observed ``false`` — a page that declares no meta description — is
website evidence and is shown as such; a measurement that was never made is shown as missing,
never as negative.
"""

from __future__ import annotations

import html
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from pxapi.domain.run_validation import REASONS, GateFamily, ReasonCode

#: The one stylesheet, served by the adapter under the page's own origin.
STYLESHEET_PATH: Final = "/operator/workbench.css"

APP_TITLE: Final = "PXAPI Operator Workbench"

#: Every reason code as written, so a code read from a receipt is looked up only when known.
REASON_VALUES: Final[frozenset[str]] = frozenset(code.value for code in ReasonCode)


class Markup(str):
    """Markup this module built. Only :func:`el`, :func:`void` and :func:`page` produce it."""

    __slots__ = ()


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _render(child: Any) -> str:
    if child is None or child is False:
        return ""
    if isinstance(child, Markup):
        return child
    if isinstance(child, list | tuple):
        return "".join(_render(item) for item in child)
    return _escape(child)


def _attribute_name(name: str) -> str:
    return name.rstrip("_").replace("_", "-")


def _attributes(attrs: Mapping[str, Any]) -> str:
    rendered = []
    for name, value in attrs.items():
        if value is None or value is False:
            continue
        if value is True:
            rendered.append(f" {_attribute_name(name)}")
        else:
            rendered.append(f' {_attribute_name(name)}="{_escape(value)}"')
    return "".join(rendered)


def el(tag: str, *children: Any, **attrs: Any) -> Markup:
    """One element. Every child that is not already :class:`Markup` is escaped as text."""
    return Markup(f"<{tag}{_attributes(attrs)}>{_render(children)}</{tag}>")


def void(tag: str, **attrs: Any) -> Markup:
    """One void element (``input``, ``meta``, ``link``). Attribute values are escaped."""
    return Markup(f"<{tag}{_attributes(attrs)}>")


# --- vocabulary shown to a person ------------------------------------------------------------

GATE_TITLES: Final[dict[GateFamily, str]] = {
    GateFamily.INPUT_CONTRACT: "Input contract",
    GateFamily.ACQUISITION_COMPLETENESS: "Acquisition completeness",
    GateFamily.CANONICAL_VALIDITY: "Canonical validity",
    GateFamily.PROVENANCE_LINKAGE: "Provenance and linkage",
    GateFamily.EVIDENCE_COVERAGE: "Evidence coverage",
    GateFamily.UNRESOLVED_CONFLICTS_LIMITATIONS: "Unresolved conflicts and limitations",
    GateFamily.ARTIFACT_BUNDLE_VALIDITY: "Artifact bundle validity",
}

#: ``state -> (symbol, word, explanation)``. The word carries the meaning; the symbol and the
#: colour only repeat it.
STATE_LABELS: Final[dict[str, tuple[str, str, str]]] = {
    "PASS": ("✓", "PASS", "checked and holds"),
    "FAIL": ("✗", "FAIL", "a defect of this service"),
    "BLOCKED": ("!", "BLOCKED", "evidence missing, incomplete or technically unavailable"),
    "NOT_APPLICABLE": ("○", "NOT APPLICABLE", "deliberately not relevant to this run"),
}


def state_badge(state: str, *, explain: bool = False) -> Markup:
    symbol, word, explanation = STATE_LABELS.get(state, ("?", state, "unrecognised state"))
    return el(
        "span",
        el("span", symbol, aria_hidden="true", class_="symbol"),
        " ",
        word,
        el("span", f" — {explanation}", class_="explain") if explain else None,
        class_=f"badge badge-{state.lower().replace('_', '-')}",
    )


def run_state_badge(state: str | None) -> Markup:
    labels = {
        "SUCCEEDED": ("run-ok", "SUCCEEDED — the run executed; this is not a release"),
        "FAILED": ("run-failed", "FAILED — the run stopped; see the failure code"),
    }
    css, text = labels.get(state or "", ("run-other", state or "unknown"))
    return el("span", text, class_=f"badge {css}")


@dataclass(frozen=True)
class AssessmentView:
    """How one measurement or evidence assessment is described to a person."""

    kind: str
    label: str


def describe_assessment(assessment: Any) -> AssessmentView:
    """Website evidence, missing evidence, not applicable or conflict — in words."""
    if not isinstance(assessment, dict):
        return AssessmentView("missing", "No assessment recorded")
    if "not_assessed_reason" in assessment:
        reason = assessment["not_assessed_reason"]
        return AssessmentView(
            "missing",
            f"Missing evidence — not assessed ({reason}); a limitation of this analysis, "
            "not a finding about the website",
        )
    state = assessment.get("result_state")
    if state == "KNOWN":
        return AssessmentView("evidence", "Website evidence — observed")
    if state == "UNKNOWN":
        return AssessmentView(
            "missing", "Missing evidence — assessed, but established nothing (UNKNOWN)"
        )
    if state == "NOT_APPLICABLE":
        return AssessmentView("not-applicable", "Not applicable to this page")
    if state == "CONFLICT":
        return AssessmentView("conflict", "Unresolved conflict")
    return AssessmentView("missing", "Unrecognised assessment")


def describe_value(measurement: Mapping[str, Any]) -> Any:
    """The measured value as text, or an em dash when the measurement carries none."""
    result = measurement.get("result")
    if not isinstance(result, dict):
        return el("span", "no value", class_="muted")
    kind = result.get("value_type")
    if kind == "BOOLEAN":
        return "yes" if result.get("boolean_value") is True else "no"
    member = {"INTEGER": "integer_value", "TEXT": "text_value", "URL": "url_value"}.get(kind)
    if member is None or member not in result:
        return el("span", "no value", class_="muted")
    return el("span", result[member], class_="value")


def describe_outcome(record: Mapping[str, Any]) -> Markup:
    outcome = record.get("acquisition_outcome")
    if outcome == "RESPONSE_RECEIVED":
        return el("span", "Response received", class_="outcome outcome-received")
    return el(
        "span",
        f"Technical limitation: {outcome} — no response was received; not a finding about the page",
        class_="outcome outcome-limitation",
    )


# --- the page skeleton ----------------------------------------------------------------------


def page(title: str, *body: Any, nav: Sequence[tuple[str, str]] = ()) -> Markup:
    """A complete document: landmarks, a skip link, one stylesheet, no script."""
    navigation = (
        el(
            "nav",
            el("ul", *(el("li", el("a", label, href=f"#{anchor}")) for anchor, label in nav)),
            aria_label="On this page",
            class_="toc",
        )
        if nav
        else None
    )
    document = el(
        "html",
        el(
            "head",
            void("meta", charset="utf-8"),
            void("meta", name="viewport", content="width=device-width, initial-scale=1"),
            void("meta", name="robots", content="noindex, nofollow"),
            el("title", f"{title} — {APP_TITLE}"),
            void("link", rel="stylesheet", href=STYLESHEET_PATH),
        ),
        el(
            "body",
            el("a", "Skip to main content", href="#main", class_="skip-link"),
            el(
                "header",
                el("p", el("a", APP_TITLE, href="/operator"), class_="brand"),
                el(
                    "p",
                    "Internal operator tool. One synchronous run at a time; results are kept in "
                    "memory only and are lost on restart.",
                    class_="tagline",
                ),
                class_="site-header",
            ),
            navigation,
            el("main", *body, id="main", tabindex="-1"),
            el(
                "footer",
                el(
                    "p",
                    "Validation evaluates one analysis result. It is not a customer release, "
                    "not a score and not a statement about the quality of any website.",
                ),
                class_="site-footer",
            ),
        ),
        lang="en",
    )
    return Markup("<!doctype html>\n" + document)


def _definition_list(rows: Iterable[tuple[str, Any]], **attrs: Any) -> Markup:
    items = []
    for term, value in rows:
        items.append(el("div", el("dt", term), el("dd", value), class_="row"))
    return el("dl", *items, **attrs)


def _table(
    caption: str, head: Sequence[str], rows: Iterable[Sequence[Any]], **attrs: Any
) -> Markup:
    return el(
        "div",
        el(
            "table",
            el("caption", caption),
            el("thead", el("tr", *(el("th", cell, scope="col") for cell in head))),
            el("tbody", *(el("tr", *(el("td", cell) for cell in row)) for row in rows)),
            **attrs,
        ),
        class_="table-wrap",
    )


# --- the start page ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FormState:
    """What the start form shows: previous input (only when safe to echo) and any errors."""

    url: str = ""
    budget: str = ""
    errors: tuple[str, ...] = ()


def start_page(
    form: FormState | None = None,
    *,
    latest_run_id: str | None = None,
    active_run_id: str | None = None,
) -> Markup:
    form = form or FormState()
    error_list = (
        el(
            "div",
            el("h2", "The analysis was not started", id="form-errors-heading"),
            el("ul", *(el("li", message) for message in form.errors)),
            role="alert",
            aria_labelledby="form-errors-heading",
            class_="notice notice-error",
            id="form-errors",
        )
        if form.errors
        else None
    )
    described_by = "url-help form-errors" if form.errors else "url-help"
    notices = []
    if active_run_id is not None:
        notices.append(
            el(
                "p",
                "A run is in progress (",
                el("code", active_run_id),
                "). Starting another one is refused until it has finished.",
                class_="notice notice-info",
            )
        )
    if latest_run_id is not None:
        notices.append(
            el(
                "p",
                "Most recent completed run: ",
                el("a", latest_run_id, href=f"/operator/runs/{latest_run_id}"),
                class_="notice",
            )
        )
    return page(
        "Start analysis",
        el("h1", "Start a multi-page analysis"),
        *notices,
        error_list,
        el(
            "form",
            el(
                "div",
                el("label", "Target URL", for_="url"),
                void(
                    "input",
                    id="url",
                    name="url",
                    type="url",
                    required=True,
                    autocomplete="off",
                    spellcheck="false",
                    inputmode="url",
                    value=form.url,
                    aria_describedby=described_by,
                    aria_invalid="true" if form.errors else None,
                ),
                el(
                    "p",
                    "An absolute public http(s) URL. Credentials in the URL, private and local "
                    "addresses are refused by the same safety policy every entry point uses.",
                    id="url-help",
                    class_="help",
                ),
                class_="field",
            ),
            el(
                "div",
                el("label", "Maximum selected pages", for_="max_selected_pages"),
                void(
                    "input",
                    id="max_selected_pages",
                    name="max_selected_pages",
                    type="number",
                    min="1",
                    step="1",
                    required=True,
                    inputmode="numeric",
                    value=form.budget,
                    aria_describedby="budget-help",
                ),
                el(
                    "p",
                    "Required, no default: the page budget you declare becomes the sampling "
                    "manifest's own selection budget. A whole number of at least 1.",
                    id="budget-help",
                    class_="help",
                ),
                class_="field",
            ),
            el("button", "Start analysis", type="submit"),
            el(
                "p",
                "The run is synchronous: discovery, selection and every page fetch finish "
                "before the result page opens, which can take a few minutes. Submitting again "
                "while a run is in progress is refused.",
                class_="help",
            ),
            method="post",
            action="/operator/runs",
            class_="start-form",
        ),
    )


# --- small pages ----------------------------------------------------------------------------


def message_page(title: str, heading: str, *paragraphs: Any, back: bool = True) -> Markup:
    return page(
        title,
        el("h1", heading),
        *(el("p", paragraph) for paragraph in paragraphs),
        el("p", el("a", "Back to the start page", href="/operator")) if back else None,
    )


# --- the result page --------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultView:
    """Everything the result page may show. Documents are present only once validated."""

    run_id: str
    target_url: str
    declared_budget: int
    envelope: Mapping[str, Any] | None
    receipt: Mapping[str, Any] | None
    withheld_contracts: tuple[str, ...]
    archive_available: bool


#: The in-page navigation of a result whose documents are shown, and of one whose documents
#: were withheld. Each names exactly the sections that page renders, so no link points nowhere.
RESULT_NAV: Final[tuple[tuple[str, str], ...]] = (
    ("overview", "Run overview"),
    ("validation", "Run validation"),
    ("limitations", "Limitations"),
    ("coverage", "Coverage"),
    ("pages", "Selected pages"),
    ("evidence", "Evidence inspector"),
    ("artifacts", "Artifacts"),
)
WITHHELD_NAV: Final[tuple[tuple[str, str], ...]] = (
    ("overview", "Run overview"),
    ("validation", "Run validation"),
    ("limitations", "Limitations"),
    ("withheld", "Documents withheld"),
    ("artifacts", "Artifacts"),
)


def result_page(view: ResultView) -> Markup:
    envelope = view.envelope
    sections: list[Any] = [
        el("h1", "Run ", el("code", view.run_id)),
        _overview(view),
        _validation(view.receipt),
        _limitations(view),
    ]
    if envelope is None:
        sections.append(_withheld(view))
    else:
        sections += [_coverage(envelope), _pages(envelope), _evidence(envelope)]
    sections.append(_artifacts(view))
    nav = WITHHELD_NAV if envelope is None else RESULT_NAV
    return page(f"Run {view.run_id}", *sections, nav=nav)


def _section(anchor: str, heading: str, *body: Any) -> Markup:
    return el(
        "section",
        el("h2", heading, id=f"{anchor}-heading"),
        *body,
        id=anchor,
        aria_labelledby=f"{anchor}-heading",
    )


def _overview(view: ResultView) -> Markup:
    envelope = view.envelope or {}
    state = envelope.get("analysis_run_state") or {}
    failure = state.get("failure") if isinstance(state, dict) else None
    receipt = view.receipt or {}
    rows: list[tuple[str, Any]] = [
        ("Target URL", el("span", view.target_url, class_="url")),
        ("Run ID", el("code", view.run_id)),
        ("Run state", run_state_badge(state.get("state")) if state else "withheld"),
    ]
    if isinstance(failure, dict):
        rows.append(("Failure code", el("code", failure.get("code"))))
    rows += [
        ("Declared page budget", str(view.declared_budget)),
        ("Entered at", state.get("entered_at", "—")),
        ("Finished at", state.get("finished_at", "—")),
        (
            "Validation",
            state_badge(str(receipt["overall_state"]), explain=True)
            if receipt
            else "withheld — the receipt failed its own contract",
        ),
    ]
    stages = envelope.get("stage_executions") or []
    return _section(
        "overview",
        "Run overview",
        _definition_list(rows, class_="facts"),
        el(
            "p",
            "Run state reports execution only. Whether the result can be relied on is the "
            "separate validation below: a SUCCEEDED run can still be BLOCKED or FAIL.",
            class_="help",
        ),
        _table(
            "Stage executions",
            ("Stage", "Status", "Started", "Finished"),
            (
                (
                    el("code", stage.get("stage_id")),
                    stage.get("status"),
                    stage.get("started_at"),
                    stage.get("finished_at", "—"),
                )
                for stage in stages
            ),
        )
        if stages
        else None,
    )


def _reason_rows(reasons: Sequence[Mapping[str, Any]]) -> Markup:
    if not reasons:
        return el("span", "No reason — the gate holds.", class_="muted")
    items = []
    for item in reasons:
        code = str(item.get("code"))
        meaning = (
            REASONS[ReasonCode(code)].meaning if code in REASON_VALUES else "Unrecognised reason."
        )
        location = (
            [
                " at ",
                el("code", item["pointer"]),
            ]
            if item.get("pointer")
            else []
        )
        rule = [" (rule ", el("code", item["rule"]), ")"] if item.get("rule") else []
        items.append(el("li", el("code", code), *location, *rule, void("br"), el("span", meaning)))
    return el("ul", *items, class_="reasons")


def _validation(receipt: Mapping[str, Any] | None) -> Markup:
    if receipt is None:
        return _section(
            "validation",
            "Run validation",
            el(
                "p",
                "The validation receipt this run produced does not satisfy its own contract and "
                "was withheld. That is a defect of this service, not a statement about the "
                "website.",
                class_="notice notice-error",
            ),
        )
    gates = receipt.get("gates", {})
    rows = []
    for family in GateFamily:
        gate = gates.get(family.value, {})
        rows.append(
            (
                el("span", GATE_TITLES[family], void("br"), el("code", family.value)),
                state_badge(str(gate.get("state"))),
                _reason_rows(gate.get("reasons", [])),
            )
        )
    return _section(
        "validation",
        "Run validation",
        el(
            "p",
            "Overall: ",
            state_badge(str(receipt.get("overall_state")), explain=True),
            ". Precedence FAIL, then BLOCKED, then PASS; NOT APPLICABLE is neutral.",
            class_="overall",
        ),
        _definition_list(
            (
                ("Receipt ID", el("code", receipt.get("receipt_id"))),
                ("Validated at", receipt.get("validated_at")),
                (
                    "Validator",
                    f"{receipt.get('validator')} {receipt.get('validator_version')}",
                ),
                ("Artifact bundle digest", el("code", receipt.get("artifact_bundle_digest"))),
            ),
            class_="facts",
        ),
        _table("Validation gates", ("Gate", "State", "Reasons"), rows, class_="gates"),
    )


def _limitations(view: ResultView) -> Markup:
    items: list[Any] = []
    manifest = (view.envelope or {}).get("sampling_manifest")
    if isinstance(manifest, dict) and manifest.get("selection_complete") is False:
        cause = (manifest.get("incompleteness") or {}).get("cause")
        items.append(
            el(
                "li",
                "The selection did not cover the site (selection_complete = false, cause ",
                el("code", cause),
                "). This is a bound of this analysis, not a property of the site.",
            )
        )
    for family in GateFamily:
        gate = ((view.receipt or {}).get("gates") or {}).get(family.value) or {}
        for item in gate.get("reasons", []):
            code = str(item.get("code"))
            if code not in REASON_VALUES:
                continue
            spec = REASONS[ReasonCode(code)]
            if spec.effect.value != "BLOCKED" or code == "SELECTION_INCOMPLETE":
                continue
            where = [" (", el("code", item["pointer"]), ")"] if item.get("pointer") else []
            items.append(el("li", el("code", code), *where, ": ", spec.meaning))
    body = (
        el("ul", *items)
        if items
        else el("p", "No technical limitation was recorded for this run.", class_="muted")
    )
    return _section(
        "limitations",
        "Limitations",
        el(
            "p",
            "Technical limitations are properties of this analysis process. None of them is a "
            "finding about the website, and missing evidence is never negative evidence.",
            class_="help",
        ),
        body,
    )


def _withheld(view: ResultView) -> Markup:
    return _section(
        "withheld",
        "Canonical documents withheld",
        el(
            "p",
            "This service produced documents that do not satisfy their own contracts, so none "
            "of the run's canonical documents is shown or offered for download. This names a "
            "defect in PXAPI and never anything about the analysed website.",
            class_="notice notice-error",
        ),
        el("p", "Contracts that failed: ", ", ".join(view.withheld_contracts) or "—"),
    )


def _coverage(envelope: Mapping[str, Any]) -> Markup:
    inventory = envelope.get("site_inventory")
    manifest = envelope.get("sampling_manifest")
    parts: list[Any] = []
    if isinstance(inventory, dict):
        candidates = inventory.get("candidates") or []
        eligible = sum(
            1 for c in candidates if (c.get("eligibility") or {}).get("state") == "ELIGIBLE"
        )
        parts.append(el("h3", "Site inventory"))
        parts.append(
            _definition_list(
                (
                    ("Target origin", el("span", inventory.get("target_origin"), class_="url")),
                    ("Candidates", str(len(candidates))),
                    ("Eligible", str(eligible)),
                    ("Excluded", str(len(candidates) - eligible)),
                    ("Inventory ID", el("code", inventory.get("inventory_id"))),
                    ("Output digest", el("code", inventory.get("output_digest"))),
                ),
                class_="facts",
            )
        )
        parts.append(
            _table(
                "Discovery sources",
                ("Source", "Outcome", "Candidates admitted"),
                (
                    (
                        el("code", source.get("source_id")),
                        source.get("outcome"),
                        str(source.get("candidate_count")),
                    )
                    for source in inventory.get("sources") or []
                ),
            )
        )
    else:
        parts.append(
            el(
                "p",
                "No site inventory: discovery did not establish a public origin for this run.",
                class_="muted",
            )
        )
    if isinstance(manifest, dict):
        complete = manifest.get("selection_complete")
        cause = (manifest.get("incompleteness") or {}).get("cause")
        parts.append(el("h3", "Sampling manifest"))
        parts.append(
            _definition_list(
                (
                    ("Mode", manifest.get("mode")),
                    ("Policy", f"{manifest.get('policy_id')} {manifest.get('policy_version')}"),
                    (
                        "Declared budget",
                        str((manifest.get("budgets") or {}).get("max_selected_pages", "none")),
                    ),
                    (
                        "selection_complete",
                        "true — the selection covers every eligible candidate"
                        if complete is True
                        else el(
                            "span",
                            "false — incomplete by a bound of this analysis (cause ",
                            el("code", cause),
                            "); not a property of the site",
                        ),
                    ),
                    ("Selected pages", str(len(manifest.get("selections") or []))),
                    ("Manifest ID", el("code", manifest.get("sampling_manifest_id"))),
                    ("Output digest", el("code", manifest.get("output_digest"))),
                ),
                class_="facts",
            )
        )
        exclusions = manifest.get("exclusions") or []
        if exclusions:
            parts.append(
                _table(
                    "Candidates not selected",
                    ("Reason", "Candidates"),
                    (
                        (el("code", item.get("reason")), str(item.get("candidate_count")))
                        for item in exclusions
                    ),
                )
            )
    return _section("coverage", "Coverage", *parts)


def _records(envelope: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [r for r in envelope.get("page_acquisitions") or [] if isinstance(r, dict)]


def _ranks(envelope: Mapping[str, Any]) -> dict[str, Any]:
    manifest = envelope.get("sampling_manifest") or {}
    return {
        item.get("url_key"): item
        for item in manifest.get("selections") or []
        if isinstance(item, dict)
    }


def _measurements_of(
    envelope: Mapping[str, Any], record: Mapping[str, Any]
) -> list[Mapping[str, Any]]:
    by_id = {
        m.get("measurement_id"): m
        for m in envelope.get("measurements") or []
        if isinstance(m, dict)
    }
    return [by_id[ref] for ref in record.get("measurement_refs") or [] if ref in by_id]


def _counts(measurements: Sequence[Mapping[str, Any]]) -> str:
    kinds = [describe_assessment(m.get("assessment")).kind for m in measurements]
    return (
        f"{kinds.count('evidence')} observed, {kinds.count('missing')} missing, "
        f"{kinds.count('not-applicable')} not applicable"
        + (f", {kinds.count('conflict')} conflict" if "conflict" in kinds else "")
    )


def _pages(envelope: Mapping[str, Any]) -> Markup:
    records = _records(envelope)
    if not records:
        return _section(
            "pages",
            "Selected pages",
            el("p", "This run acquired no page.", class_="muted"),
        )
    ranks = _ranks(envelope)
    rows = []
    for record in records:
        selection = ranks.get(record.get("url_key")) or {}
        body_facts = (
            ("truncated at our byte bound" if record.get("body_truncated") else "complete")
            if record.get("acquisition_outcome") == "RESPONSE_RECEIVED"
            else "—"
        )
        rows.append(
            (
                str(selection.get("selection_rank", "—")),
                el("span", record.get("url_key"), class_="url"),
                selection.get("stratum", "—"),
                describe_outcome(record),
                str(record.get("http_status", "—")),
                str(record.get("redirect_count", "—")),
                body_facts,
                _counts(_measurements_of(envelope, record)),
            )
        )
    return _section(
        "pages",
        "Selected pages",
        el(
            "p",
            "Every page the sampling manifest selected, attempted once, in selection-rank "
            "order. An HTTP status is a measured fact about a received response; a missing "
            "response is a technical limitation.",
            class_="help",
        ),
        _table(
            "Selected pages and acquisition outcomes",
            (
                "Rank",
                "Page",
                "Stratum",
                "Acquisition outcome",
                "HTTP status",
                "Redirects",
                "Body",
                "Measurements",
            ),
            rows,
        ),
    )


#: ``(css kind, term, meaning)`` for the evidence legend. Words carry the distinction; the
#: border style and colour only repeat it.
LEGEND: Final[tuple[tuple[str, str, str], ...]] = (
    (
        "evidence",
        "Website evidence",
        "an assessment that observed a value on the page \u2014 an observed \u201cno\u201d "
        "included",
    ),
    (
        "missing",
        "Missing evidence",
        "not assessed, or UNKNOWN \u2014 a limitation of this analysis, never negative evidence",
    ),
    ("not-applicable", "Not applicable", "the measurement does not apply to this page"),
    ("conflict", "Unresolved conflict", "two observations disagree and nothing resolved them"),
)


def _evidence_for(envelope: Mapping[str, Any]) -> dict[Any, list[Mapping[str, Any]]]:
    found: dict[Any, list[Mapping[str, Any]]] = {}
    for item in envelope.get("website_evidence") or []:
        if not isinstance(item, dict):
            continue
        for ref in item.get("measurement_refs") or []:
            found.setdefault(ref, []).append(item)
    return found


def _evidence(envelope: Mapping[str, Any]) -> Markup:
    records = _records(envelope)
    ranks = _ranks(envelope)
    evidence_for = _evidence_for(envelope)
    legend = el(
        "dl",
        *(
            el("div", el("dt", term), el("dd", meaning), class_=f"row kind-{kind}")
            for kind, term, meaning in LEGEND
        ),
        class_="legend",
        aria_label="Legend",
    )
    blocks = []
    for index, record in enumerate(records):
        selection = ranks.get(record.get("url_key")) or {}
        measurements = _measurements_of(envelope, record)
        rows = []
        for measurement in measurements:
            view = describe_assessment(measurement.get("assessment"))
            linked = evidence_for.get(measurement.get("measurement_id"), [])
            rows.append(
                (
                    el("code", measurement.get("metric_id")),
                    el("span", view.label, class_=f"kind kind-{view.kind}"),
                    describe_value(measurement),
                    el("code", measurement.get("measurement_id")),
                    el(
                        "ul",
                        *(
                            el(
                                "li",
                                el("code", item.get("evidence_id")),
                                " ",
                                el("span", item.get("scenario"), class_="muted"),
                            )
                            for item in linked
                        ),
                        class_="plain",
                    )
                    if linked
                    else el("span", "no evidence names this measurement", class_="muted"),
                )
            )
        withheld = record.get("measurements_withheld_reason")
        body: list[Any] = [
            _definition_list(
                (
                    ("Acquisition ID", el("code", record.get("acquisition_id"))),
                    ("Acquisition outcome", describe_outcome(record)),
                    ("Final URL", el("span", record.get("final_url_key", "—"), class_="url")),
                    ("Body digest", el("code", record.get("body_digest", "—"))),
                ),
                class_="facts",
            )
        ]
        if withheld:
            body.append(
                el(
                    "p",
                    f"Measurements withheld ({withheld}): this page's URL cannot be carried by "
                    "the contracts. A limitation of this analysis, not of the page.",
                    class_="notice",
                )
            )
        if rows:
            body.append(
                _table(
                    "Page → measurement → website evidence",
                    ("Metric", "Assessment", "Value", "Measurement", "Website evidence"),
                    rows,
                )
            )
        blocks.append(
            el(
                "details",
                el(
                    "summary",
                    f"Rank {selection.get('selection_rank', index + 1)}: ",
                    el("span", record.get("url_key"), class_="url"),
                    " — ",
                    _counts(measurements),
                ),
                *body,
                class_="page-evidence",
            )
        )
    return _section(
        "evidence",
        "Evidence inspector",
        el(
            "p",
            "Open a page to follow its chain: acquisition record, then each measurement, then "
            "the website evidence that rests on it. Values are shown exactly as measured, as "
            "text; nothing on this page is rendered from the website as markup.",
            class_="help",
        ),
        legend,
        *blocks,
    )


def _artifacts(view: ResultView) -> Markup:
    base = f"/operator/runs/{view.run_id}"
    links = []
    if view.archive_available:
        links.append(
            el(
                "li",
                el(
                    "a",
                    "Download the canonical artifact bundle (zip)",
                    href=f"{base}/artifacts.zip",
                ),
                " \u2014 the run's canonical documents, byte for byte as validated. The receipt "
                "pins them by digest and is downloaded on its own.",
            )
        )
    else:
        links.append(
            el(
                "li",
                "The canonical artifact bundle is withheld for this run.",
                class_="muted",
            )
        )
    if view.receipt is not None:
        links.append(
            el(
                "li",
                el(
                    "a",
                    "Download the validation receipt (analysis-validation-receipt.v1)",
                    href=f"{base}/analysis-validation-receipt.json",
                ),
            )
        )
    return _section(
        "artifacts",
        "Artifacts",
        el("ul", *links),
        el(
            "p",
            "Kept in this process's memory only, for the most recent completed run. A restart "
            "or a newer run discards it.",
            class_="help",
        ),
    )


# --- the stylesheet -------------------------------------------------------------------------

#: The stylesheet ships beside this module as a plain file, so it is reviewable as CSS and never
#: assembled from strings. It holds no ``url()``, no ``@import`` and no remote reference.
STYLESHEET: Final = (Path(__file__).parent / "workbench.css").read_text(encoding="utf-8")
