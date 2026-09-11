"""Every closed vocabulary in the registry is pinned as a whole set, not one token at a time.

An invalid fixture proves that *one* token is rejected. It never pins the *set*: widening a
closed enum with any token no fixture happens to use leaves every fixture green, because each
fixture only ever asserts about the value it carries. That is not a theory about this suite —
it was measured on this tree with every other test of this slice already in place. A third
``scan_mode`` (``AUTHENTICATED_DEEP``), a fifth stage ``status`` (``PAUSED``) and a fourth
member of the run state's terminal condition (``CREATED``) each left ``pytest`` at 449 passed,
rc 0. The stage-status and stage-terminal widenings were caught only when the added token
happened to collide with the token a fixture already used, which is luck, not a gate.

This module closes that gap in two ways. It states each closed vocabulary once and in full,
and — the part that still holds when a later slice adds a contract — it fails when a closed
vocabulary appears anywhere in the registry that nobody has pinned. Where a vocabulary has a
source of truth in the Domain it is derived from it rather than copied, so a pin here cannot
drift from the code it pins; where a generic registry rule already owns a vocabulary, this
module names that rule instead of restating the fact a second time.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from pxapi.domain.run_state import TERMINAL_STATES, RunState
from tests.contracts.support import CONTRACTS, load_json

ROOT = Path(__file__).resolve().parents[1]

#: The global run state vocabulary and its terminal subset are *derived* from the Domain. The
#: schema is the second statement of a fact the code owns, so the expectation must be too.
RUN_STATES: list[str] = [state.value for state in RunState]
RUN_TERMINAL: list[str] = [name for name in RUN_STATES if RunState(name) in TERMINAL_STATES]

#: A stage execution's own status vocabulary has no Domain source of truth, and deliberately
#: so: the Domain knows nothing about stages. The literal here therefore *is* the pin. There is
#: no ``PENDING`` and no ``QUEUED`` — a record exists only once the stage has begun.
STAGE_STATUSES: list[str] = ["RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"]

#: A stage has finished exactly when its status is not ``RUNNING``, so the conditional that
#: requires ``finished_at`` is derived from the status vocabulary rather than restated.
STAGE_TERMINAL: list[str] = [name for name in STAGE_STATUSES if name != "RUNNING"]

#: The two accepted operating modes. The vocabulary is closed, mandatory and case-sensitive:
#: a run whose authorised mode was never stated is not a valid request, and an invented
#: third mode is rejected by the contract before any component could act on it.
SCAN_MODES: list[str] = ["PUBLIC_NON_INVASIVE", "OWNER_VERIFIED_CONTROLLED"]

#: How a performed assessment collected its result. Neither value means "not assessed": whether
#: an assessment happened at all is a separate member, so absence is never inferred from a mode.
COLLECTION_MODES: list[str] = ["MEASURED", "OBSERVED"]

#: What a performed assessment established. ``KNOWN`` is the only state that carries a website
#: value; the other three are outcomes about the assessment, not findings about the site.
RESULT_STATES: list[str] = ["KNOWN", "UNKNOWN", "CONFLICT", "NOT_APPLICABLE"]

#: Why an assessment never happened. Every reason names the analysis process — a provider, our
#: own runtime, a permission, a time budget, an unsupported subject, or nobody having asked —
#: and none of them says anything about the website. That is what makes the set closed: an open
#: token could carry a reason that does.
NOT_ASSESSED_REASONS: list[str] = [
    "PROVIDER_FAILURE",
    "RUNTIME_ERROR",
    "PERMISSION_DENIED",
    "TIMEOUT",
    "UNSUPPORTED",
    "NOT_REQUESTED",
]

#: Whether evidence speaks for or against the website. There is deliberately no ``NEUTRAL``: a
#: KNOWN observation carrying no judgement omits the member, so nobody has to decide what a
#: neutral verdict would mean.
POLARITIES: list[str] = ["POSITIVE", "NEGATIVE"]

#: The types a measured value may take, chosen by the result's own ``value_type`` discriminator.
#: The set is closed, which is what keeps the value from becoming an open node.
VALUE_TYPES: list[str] = ["BOOLEAN", "INTEGER", "TEXT", "URL"]

#: What became of an attempted discovery source. Every token names the analysis process — a
#: source that was read, was well formed and declared nothing, was not served, could not be
#: parsed, declared no sitemap, hit one of our own bounds, was refused by our own target policy,
#: failed in a provider or in our own runtime, or ran out of time. The set is closed because
#: each token carries its own rule about whether a non-zero admitted count is even possible, and
#: because an open token could arrive carrying a reason that describes the website instead.
SOURCE_OUTCOMES: list[str] = [
    "USED",
    "EMPTY",
    "ABSENT",
    "MALFORMED",
    "NO_SITEMAP_DECLARATION",
    "BUDGET_EXHAUSTED",
    "TARGET_POLICY_REFUSED",
    "PROVIDER_FAILURE",
    "RUNTIME_ERROR",
    "TIMEOUT",
]

#: The outcomes under which the inventory could actually have admitted a candidate from the
#: source: it was read, or it was cut short part-way by one of our bounds or by the clock. Every
#: other outcome is pinned to an admitted count of zero, so an absent, malformed, undeclared,
#: refused or failed source is structurally incapable of reporting that it contributed pages.
#: Derived by membership rather than restated, so the subset cannot drift from the vocabulary.
ADMITTING_SOURCE_OUTCOMES: list[str] = [
    outcome for outcome in SOURCE_OUTCOMES if outcome in {"USED", "BUDGET_EXHAUSTED", "TIMEOUT"}
]

#: What every other outcome's admitted count is pinned to.
NO_ADMISSION_COUNT = 0

#: Whether a discovered candidate is a technically admissible acquisition target. Two values,
#: and an admissibility statement only: EXCLUDED means this analysis will not fetch it, never
#: that the page is deficient.
ELIGIBILITY_STATES: list[str] = ["ELIGIBLE", "EXCLUDED"]

#: The one state that may carry a reason. Stated once and pinned at the conditional below.
EXCLUDED_ELIGIBILITY_STATE = "EXCLUDED"

#: Why a discovered candidate is not a technically admissible target. Every token names this
#: analysis or the discovery boundary it was authorised for, never a quality of the page.
CANDIDATE_EXCLUSION_REASONS: list[str] = [
    "OFF_ORIGIN",
    "NON_PAGE_RESOURCE",
    "TARGET_POLICY_REFUSED",
    "BUDGET_EXHAUSTED",
    "UNSUPPORTED",
]

#: How a sampling manifest's population was chosen. The threshold at which a site moves from a
#: census to a sample is deliberately absent from the contracts and from this module: it is an
#: open, benchmark-dependent policy decision, and STRATIFIED_SAMPLE existing in the vocabulary
#: is not a claim that a benchmark-authorised sample can currently be produced.
SAMPLING_MODES: list[str] = ["CENSUS", "STRATIFIED_SAMPLE"]

#: Why a deterministic policy took one candidate. None of the three ranks a page above another.
SELECTION_REASONS: list[str] = ["SEED", "CENSUS", "STRATUM_QUOTA"]

#: Why inventory candidates were not selected. Not being selected is a fact about this run's
#: method and budgets, never a defect of the pages concerned.
SELECTION_EXCLUSION_REASONS: list[str] = [
    "NOT_SELECTED_BY_POLICY",
    "SELECTION_BUDGET_EXHAUSTED",
    "INELIGIBLE_IN_INVENTORY",
]

#: Which technical limitation of the run stopped a selection before the policy's own defined end.
#: The set is closed for the reason every other neutrality vocabulary here is closed: an open
#: token could arrive carrying a reason that describes the website, and this member exists
#: precisely so that an incomplete selection stays attributable to a bound of ours. It covers a
#: declared budget, a safety bound and the runtime, which is the minimum the authority requires.
INCOMPLETENESS_CAUSES: list[str] = [
    "SELECTION_BUDGET_EXHAUSTED",
    "SAFETY_LIMIT_REACHED",
    "RUNTIME_LIMIT_REACHED",
]

#: The completeness value that admits — and requires — an incompleteness cause. Stated once and
#: pinned at the conditional below, so the branch cannot be flipped without a red test.
INCOMPLETE_SELECTION_VALUE = False

#: The one cause that drags a further requirement with it: a declared budget said to be exhausted
#: must be a budget the manifest actually declares. It is a **literal**, exactly as
#: ``VALUED_RESULT_STATE`` below is, and deliberately not derived from the vocabulary above: a
#: value selected out of that list is a member of it by construction, so the companion membership
#: canary would be true no matter what either declaration said, and a token dropped from the
#: vocabulary would raise at import time instead of failing the test that exists to catch it.
BUDGET_INCOMPLETENESS_CAUSE = "SELECTION_BUDGET_EXHAUSTED"

#: The one result state that carries a value about the website. Both carriers key a conditional
#: on it — a measurement may hold a result, and evidence may hold a polarity, only here — so it
#: is stated once and pinned at both sites through the pointer below.
VALUED_RESULT_STATE = "KNOWN"
VALUED_STATE_POINTER = "#/allOf/0/if/properties/assessment/properties/result_state/const"

#: Where the inventory's source and eligibility vocabularies live. They are stated here rather
#: than inline in the pin table because each is long enough that an inline literal would hide
#: which vocabulary is being pinned.
_SOURCE_ITEM = "#/properties/sources/items"
_ELIGIBILITY = "#/properties/candidates/items/properties/eligibility"
SOURCE_OUTCOME_POINTER = f"{_SOURCE_ITEM}/properties/outcome/enum"
ADMITTING_OUTCOME_POINTER = f"{_SOURCE_ITEM}/allOf/0/if/properties/outcome/enum"
NO_ADMISSION_POINTER = f"{_SOURCE_ITEM}/allOf/0/else/properties/candidate_count/const"
ELIGIBILITY_STATE_POINTER = f"{_ELIGIBILITY}/properties/state/enum"
CANDIDATE_EXCLUSION_POINTER = f"{_ELIGIBILITY}/properties/exclusion_reason/enum"
EXCLUDED_STATE_POINTER = f"{_ELIGIBILITY}/allOf/0/if/properties/state/const"

#: Where the manifest's incompleteness vocabulary and the two conditionals that key on it live.
_INCOMPLETENESS = "#/properties/incompleteness"
INCOMPLETENESS_CAUSE_POINTER = f"{_INCOMPLETENESS}/properties/cause/enum"
INCOMPLETE_SELECTION_POINTER = "#/allOf/0/if/properties/selection_complete/const"
BUDGET_CAUSE_POINTER = "#/allOf/1/if/properties/incompleteness/properties/cause/const"

#: Every closed vocabulary this module pins, as ``(schema file, JSON pointer) -> exact value``.
PINNED: dict[tuple[str, str], Any] = {
    ("analysis-run-request.v1.json", "#/properties/scan_mode/enum"): SCAN_MODES,
    ("analysis-run-state.v1.json", "#/properties/state/enum"): RUN_STATES,
    ("analysis-run-state.v1.json", "#/allOf/0/if/properties/state/enum"): RUN_TERMINAL,
    ("analysis-run-state.v1.json", "#/allOf/1/if/properties/state/const"): "FAILED",
    ("stage-execution-record.v1.json", "#/properties/status/enum"): STAGE_STATUSES,
    ("stage-execution-record.v1.json", "#/allOf/0/if/properties/status/enum"): STAGE_TERMINAL,
    ("assessment.v1.json", "#/$defs/collection_mode/enum"): COLLECTION_MODES,
    ("assessment.v1.json", "#/$defs/result_state/enum"): RESULT_STATES,
    ("assessment.v1.json", "#/$defs/not_assessed_reason/enum"): NOT_ASSESSED_REASONS,
    ("measurement-record.v1.json", "#/properties/result/properties/value_type/enum"): VALUE_TYPES,
    ("measurement-record.v1.json", VALUED_STATE_POINTER): VALUED_RESULT_STATE,
    ("website-evidence.v1.json", "#/properties/polarity/enum"): POLARITIES,
    ("website-evidence.v1.json", VALUED_STATE_POINTER): VALUED_RESULT_STATE,
    ("site-inventory.v1.json", SOURCE_OUTCOME_POINTER): SOURCE_OUTCOMES,
    ("site-inventory.v1.json", ADMITTING_OUTCOME_POINTER): ADMITTING_SOURCE_OUTCOMES,
    ("site-inventory.v1.json", NO_ADMISSION_POINTER): NO_ADMISSION_COUNT,
    ("site-inventory.v1.json", ELIGIBILITY_STATE_POINTER): ELIGIBILITY_STATES,
    ("site-inventory.v1.json", CANDIDATE_EXCLUSION_POINTER): CANDIDATE_EXCLUSION_REASONS,
    ("site-inventory.v1.json", EXCLUDED_STATE_POINTER): EXCLUDED_ELIGIBILITY_STATE,
    ("sampling-manifest.v1.json", "#/properties/mode/enum"): SAMPLING_MODES,
    ("sampling-manifest.v1.json", "#/$defs/selection_reason/enum"): SELECTION_REASONS,
    ("sampling-manifest.v1.json", "#/$defs/exclusion_reason/enum"): SELECTION_EXCLUSION_REASONS,
    ("sampling-manifest.v1.json", INCOMPLETENESS_CAUSE_POINTER): INCOMPLETENESS_CAUSES,
    ("sampling-manifest.v1.json", INCOMPLETE_SELECTION_POINTER): INCOMPLETE_SELECTION_VALUE,
    ("sampling-manifest.v1.json", BUDGET_CAUSE_POINTER): BUDGET_INCOMPLETENESS_CAUSE,
    # The four value_type branches, derived from the vocabulary rather than listed: this pins
    # that there is exactly one branch per declared type, in the declared order, so a fifth
    # type cannot arrive without a branch and a branch cannot be dropped without a red test.
    **{
        (
            "measurement-record.v1.json",
            f"#/properties/result/allOf/{index}/if/properties/value_type/const",
        ): value_type
        for index, value_type in enumerate(VALUE_TYPES)
    },
}

#: The one vocabulary a generic registry rule already owns: every contract's ``schema_version``
#: is pinned against that contract's registered version, for every contract, by the test named
#: here. Naming the owner keeps the coverage test below complete without stating the fact
#: twice, and the owner is checked to exist so a delegation cannot go stale.
VERSION_POINTER = "#/properties/schema_version/const"
VERSION_OWNER = (
    "tests/contracts/test_schema_meta.py",
    "test_every_contract_is_a_closed_object_pinning_its_own_version",
)
PINNED_ELSEWHERE: dict[tuple[str, str], tuple[str, str]] = {
    (Path(entry["schema"]).name, VERSION_POINTER): VERSION_OWNER for entry in CONTRACTS.entries()
}


def iter_vocabularies(node: Any, path: str = "#") -> Iterator[tuple[str, Any]]:
    """Every ``enum`` and ``const`` in a schema, as ``(JSON pointer, declared value)``."""
    if isinstance(node, dict):
        for keyword in ("enum", "const"):
            if keyword in node:
                yield f"{path}/{keyword}", node[keyword]
        for key, value in node.items():
            yield from iter_vocabularies(value, f"{path}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from iter_vocabularies(value, f"{path}/{index}")


def declared_vocabularies() -> dict[tuple[str, str], Any]:
    """Every closed vocabulary in every schema the manifest names. The inventory is the data."""
    return {
        (path.name, pointer): value
        for path in CONTRACTS.all_schema_paths()
        for pointer, value in iter_vocabularies(load_json(path))
    }


DECLARED = declared_vocabularies()
PINNED_IDS = [f"{name}{pointer}" for name, pointer in PINNED]


def _pin_id(item: tuple[tuple[str, str], Any]) -> str:
    (name, pointer), _ = item
    return f"{name}{pointer}"


# --- the pins ---------------------------------------------------------------------------------


@pytest.mark.parametrize("item", sorted(PINNED.items()), ids=_pin_id)
def test_a_pinned_vocabulary_is_exactly_what_this_module_declares(
    item: tuple[tuple[str, str], Any],
) -> None:
    """Not a subset and not a superset: widening or narrowing the set fails here."""
    (name, pointer), expected = item
    assert DECLARED[(name, pointer)] == expected, (
        f"{name}{pointer}: the registry declares {DECLARED[(name, pointer)]!r}, "
        f"this module pins {expected!r}"
    )


def test_every_closed_vocabulary_in_the_registry_is_pinned_or_delegated() -> None:
    """A closed vocabulary nobody pinned is the hole this module exists to close."""
    covered = set(PINNED) | set(PINNED_ELSEWHERE)
    unpinned = sorted(set(DECLARED) - covered)
    stale = sorted(covered - set(DECLARED))
    assert unpinned == [], f"closed vocabularies nobody pins: {unpinned}"
    assert stale == [], f"pinned vocabularies the registry no longer declares: {stale}"


@pytest.mark.parametrize("owner", sorted(set(PINNED_ELSEWHERE.values())), ids=lambda o: o[1])
def test_a_delegated_vocabulary_names_a_test_that_exists(owner: tuple[str, str]) -> None:
    """A delegation to a test that was renamed or deleted would exempt a vocabulary silently."""
    relative, function = owner
    source = (ROOT / relative).read_text(encoding="utf-8")
    assert f"def {function}(" in source, f"{relative} declares no {function}"


# --- the canaries -----------------------------------------------------------------------------


def test_the_admitting_outcomes_are_a_proper_subset_of_the_source_vocabulary() -> None:
    """A subset that grew to the whole set would exempt every outcome from the zero rule."""
    assert ADMITTING_SOURCE_OUTCOMES, "no outcome may admit a candidate; the rule is vacuous"
    assert set(ADMITTING_SOURCE_OUTCOMES) < set(SOURCE_OUTCOMES)


def test_the_excluded_state_belongs_to_the_eligibility_vocabulary() -> None:
    """The token the eligibility conditional keys on must be one the vocabulary declares."""
    assert EXCLUDED_ELIGIBILITY_STATE in ELIGIBILITY_STATES


def test_no_sampling_vocabulary_encodes_a_census_threshold() -> None:
    """The census-to-sampling threshold is MISSING and must not arrive as a token or a number."""
    tokens = SAMPLING_MODES + SELECTION_REASONS + INCOMPLETENESS_CAUSES
    assert all(not token.strip("_").isdigit() for token in tokens)
    assert SAMPLING_MODES == ["CENSUS", "STRATIFIED_SAMPLE"]


def test_the_incompleteness_vocabulary_covers_budget_safety_and_runtime() -> None:
    """The authority requires at least those three limitation kinds to be expressible.

    The check is over the kind each token names rather than over the literal set, so renaming a
    token is free while *losing* one of the three required kinds is not.
    """
    required = {"BUDGET": False, "SAFETY": False, "RUNTIME": False}
    for cause in INCOMPLETENESS_CAUSES:
        for kind in required:
            if kind in cause:
                required[kind] = True
    unmet = sorted(kind for kind, covered in required.items() if not covered)
    assert unmet == [], f"no incompleteness cause names a {unmet} limitation"


def test_the_budget_incompleteness_cause_belongs_to_the_incompleteness_vocabulary() -> None:
    """The token the budget conditional keys on must be one the vocabulary actually declares."""
    assert BUDGET_INCOMPLETENESS_CAUSE in INCOMPLETENESS_CAUSES


def test_the_incomplete_selection_value_is_the_false_branch_of_a_boolean() -> None:
    """The conditional keys on ``false``; keying it on ``true`` would invert the whole rule."""
    assert INCOMPLETE_SELECTION_VALUE is False


def test_the_valued_result_state_belongs_to_the_result_state_vocabulary() -> None:
    """The token both carriers key on must be one the vocabulary actually declares."""
    assert VALUED_RESULT_STATE in RESULT_STATES


def test_the_registry_declares_something_to_pin() -> None:
    """An empty inventory would make every assertion above vacuously true."""
    assert len(DECLARED) >= len(PINNED) + len(PINNED_ELSEWHERE) > 0


def test_the_vocabulary_scanner_finds_a_planted_vocabulary() -> None:
    """The scanner is proven to see an ``enum`` and a ``const``, nested and inside a list."""
    planted = {
        "properties": {"mode": {"const": "PLANTED"}},
        "allOf": [{"if": {"properties": {"mode": {"enum": ["PLANTED", "OTHER"]}}}}],
    }
    found = dict(iter_vocabularies(planted))
    assert found["#/properties/mode/const"] == "PLANTED"
    assert found["#/allOf/0/if/properties/mode/enum"] == ["PLANTED", "OTHER"]


def test_the_coverage_rule_reports_a_vocabulary_the_pins_do_not_cover() -> None:
    """Canary for the coverage test: an unpinned vocabulary is reported, never absorbed.

    Deliberately synthetic. Planting into the real inventory would make this canary fail
    alongside the rule it guards, which proves nothing about the rule.
    """
    planted = ("planted.v1.json", "#/properties/x/enum")
    covered = set(PINNED) | set(PINNED_ELSEWHERE)
    assert sorted({planted} - covered) == [planted]
