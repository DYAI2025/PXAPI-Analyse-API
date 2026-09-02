"""Q / R: the Pass-1 projection resolves every completion order to the same canonical state.

Pass 1 runs Baseline Collection and Business Research concurrently. The projection must
depend only on the record set — never on which stage finished first — and a failure of either
stage must land in its own canonical failure state, always through an approved edge.
"""

from __future__ import annotations

import contextlib
from itertools import permutations

import pytest

from pxapi.domain.run_state import ALLOWED_TRANSITIONS, RunState
from pxapi.domain.stage_execution import (
    FAILURE_STATE_FOR,
    PASS_ONE_STAGES,
    InconsistentStageRecords,
    Stage,
    StageExecution,
    StageStatus,
    project_pass_one,
)

B, R = Stage.BASELINE_COLLECTION, Stage.BUSINESS_RESEARCH
P, RUN, OK, FAIL, CANC = (
    StageStatus.PENDING,
    StageStatus.RUNNING,
    StageStatus.SUCCEEDED,
    StageStatus.FAILED,
    StageStatus.CANCELLED,
)


def records(baseline: StageStatus | None, research: StageStatus | None) -> list[StageExecution]:
    """Records for the two Pass-1 stages; ``None`` means no record exists for that stage."""
    result = []
    if baseline is not None:
        result.append(StageExecution(B, baseline))
    if research is not None:
        result.append(StageExecution(R, research))
    return result


# --- vocabulary ---------------------------------------------------------------------------------


def test_stage_vocabulary_is_the_ten_activities_in_canonical_order() -> None:
    assert [s.value for s in Stage] == [
        "BASELINE_COLLECTION",
        "BUSINESS_RESEARCH",
        "TARGETED_COLLECTION",
        "SYNTHESIS",
        "SCORING",
        "PRODUCT_DIAGNOSIS",
        "CUSTOMER_PROJECTION",
        "RENDERING",
        "VALIDATION",
        "DELIVERY",
    ]
    assert {B, R} == PASS_ONE_STAGES


def test_every_stage_maps_to_exactly_one_coarse_failure_state() -> None:
    assert set(FAILURE_STATE_FOR) == set(Stage)
    assert FAILURE_STATE_FOR == {
        Stage.BASELINE_COLLECTION: RunState.FAILED_COLLECTION,
        Stage.BUSINESS_RESEARCH: RunState.FAILED_RESEARCH,
        Stage.TARGETED_COLLECTION: RunState.FAILED_COLLECTION,
        Stage.SYNTHESIS: RunState.FAILED_SYNTHESIS,
        Stage.SCORING: RunState.FAILED_SYNTHESIS,
        Stage.PRODUCT_DIAGNOSIS: RunState.FAILED_SYNTHESIS,
        Stage.CUSTOMER_PROJECTION: RunState.FAILED_SYNTHESIS,
        Stage.RENDERING: RunState.FAILED_VALIDATION,
        Stage.VALIDATION: RunState.FAILED_VALIDATION,
        Stage.DELIVERY: RunState.DELIVERY_FAILED,
    }
    # BLOCKED_INPUT happens before any stage and is therefore no stage's failure state.
    assert RunState.BLOCKED_INPUT not in set(FAILURE_STATE_FOR.values())


# --- the named Pass-1 consequences -------------------------------------------------------------


@pytest.mark.parametrize(
    ("baseline", "research", "expected"),
    [
        (None, None, RunState.COLLECTING_BASELINE),  # VERIFIED starts Pass 1; nothing recorded yet
        (P, P, RunState.COLLECTING_BASELINE),
        (RUN, P, RunState.COLLECTING_BASELINE),
        (RUN, RUN, RunState.COLLECTING_BASELINE),
        (RUN, OK, RunState.COLLECTING_BASELINE),  # research done first: still collecting
        (P, OK, RunState.COLLECTING_BASELINE),
        (None, OK, RunState.COLLECTING_BASELINE),
        (OK, P, RunState.BUSINESS_RESEARCH),  # baseline done, research not started
        (OK, None, RunState.BUSINESS_RESEARCH),
        (OK, RUN, RunState.BUSINESS_RESEARCH),
        (OK, OK, RunState.COLLECTING_TARGETED),
        (FAIL, P, RunState.FAILED_COLLECTION),
        (FAIL, CANC, RunState.FAILED_COLLECTION),
        (FAIL, OK, RunState.FAILED_COLLECTION),
        (FAIL, None, RunState.FAILED_COLLECTION),
        (P, FAIL, RunState.FAILED_RESEARCH),
        (CANC, FAIL, RunState.FAILED_RESEARCH),
        (OK, FAIL, RunState.FAILED_RESEARCH),
        (None, FAIL, RunState.FAILED_RESEARCH),
        (FAIL, FAIL, RunState.FAILED_COLLECTION),  # both failed: canonical order decides
    ],
    ids=lambda v: getattr(v, "value", str(v)),
)
def test_projection_of_each_record_set(
    baseline: StageStatus | None, research: StageStatus | None, expected: RunState
) -> None:
    assert project_pass_one(records(baseline, research)) is expected


def test_projection_is_independent_of_record_order() -> None:
    for baseline in StageStatus:
        for research in StageStatus:
            recs = records(baseline, research)
            outcomes = set()
            for order in permutations(recs):
                try:
                    outcomes.add(project_pass_one(order))
                except InconsistentStageRecords:
                    outcomes.add("inconsistent")
            assert len(outcomes) == 1, (baseline, research, outcomes)


# --- Q: every interleaving of the Pass-1 events resolves through approved edges ---------------

EVENTS = ("baseline.start", "baseline.end", "research.start", "research.end")


def _interleavings() -> list[tuple[str, ...]]:
    """Every ordering of the four events in which each stage starts before it ends."""
    valid = []
    for order in permutations(EVENTS):
        if order.index("baseline.start") < order.index("baseline.end") and order.index(
            "research.start"
        ) < order.index("research.end"):
            valid.append(order)
    return valid


def _apply(state: dict[Stage, StageStatus], event: str, outcome: StageStatus) -> bool:
    """Apply one event; return False when the path has ended (a stage failed)."""
    stage = B if event.startswith("baseline") else R
    if event.endswith("start"):
        state[stage] = RUN
        return True
    state[stage] = outcome
    if outcome is FAIL:
        other = R if stage is B else B
        if state.get(other) is RUN:
            state[other] = CANC
        return False
    return True


@pytest.mark.parametrize("order", _interleavings(), ids=lambda o: " > ".join(o))
@pytest.mark.parametrize(
    ("baseline_outcome", "research_outcome"),
    [(OK, OK), (OK, FAIL), (FAIL, OK), (FAIL, FAIL)],
    ids=["ok/ok", "ok/fail", "fail/ok", "fail/fail"],
)
def test_every_interleaving_walks_approved_edges_to_the_canonical_result(
    order: tuple[str, ...], baseline_outcome: StageStatus, research_outcome: StageStatus
) -> None:
    assert len(_interleavings()) == 6  # canary: 4!/(2*2) orderings
    state: dict[Stage, StageStatus] = {}
    previous = RunState.VERIFIED
    projected = project_pass_one([StageExecution(s, st) for s, st in state.items()])
    assert projected is RunState.COLLECTING_BASELINE
    assert projected in ALLOWED_TRANSITIONS[previous]
    previous = projected
    ended = False
    for event in order:
        outcome = baseline_outcome if event.startswith("baseline") else research_outcome
        alive = _apply(state, event, outcome)
        projected = project_pass_one([StageExecution(s, st) for s, st in state.items()])
        assert projected is previous or projected in ALLOWED_TRANSITIONS[previous], (
            f"{event}: {previous.value} -> {projected.value} is not an approved edge"
        )
        previous = projected
        if not alive:
            ended = True
            break
    first_failure = next(
        (
            event
            for event in order
            if event.endswith("end")
            and (baseline_outcome if event.startswith("baseline") else research_outcome) is FAIL
        ),
        None,
    )
    if first_failure is None:
        assert not ended
        assert previous is RunState.COLLECTING_TARGETED
    else:
        assert ended
        failed_stage = B if first_failure.startswith("baseline") else R
        assert previous is FAILURE_STATE_FOR[failed_stage]


# --- R: the two Pass-1 failures are distinct canonical states --------------------------------


def test_baseline_and_research_failures_are_distinct_states() -> None:
    baseline_failed = project_pass_one(records(FAIL, CANC))
    research_failed = project_pass_one(records(CANC, FAIL))
    assert baseline_failed is RunState.FAILED_COLLECTION
    assert research_failed is RunState.FAILED_RESEARCH
    assert baseline_failed is not research_failed


# --- fail-closed inputs -------------------------------------------------------------------------


def test_duplicate_stage_records_are_rejected() -> None:
    with pytest.raises(InconsistentStageRecords, match="duplicate"):
        project_pass_one([StageExecution(B, RUN), StageExecution(B, OK)])


@pytest.mark.parametrize("stage", sorted(set(Stage) - PASS_ONE_STAGES, key=lambda s: s.value))
def test_records_outside_pass_one_are_rejected(stage: Stage) -> None:
    with pytest.raises(InconsistentStageRecords, match="outside Pass 1"):
        project_pass_one([StageExecution(B, OK), StageExecution(R, OK), StageExecution(stage, OK)])


@pytest.mark.parametrize(
    ("baseline", "research"), [(CANC, OK), (OK, CANC), (CANC, P), (CANC, CANC)]
)
def test_cancelled_without_a_failed_sibling_is_rejected(
    baseline: StageStatus, research: StageStatus
) -> None:
    with pytest.raises(InconsistentStageRecords, match="CANCELLED"):
        project_pass_one(records(baseline, research))


def test_unknown_stage_or_status_strings_are_rejected() -> None:
    with pytest.raises(ValueError, match="RESEARCHING"):
        project_pass_one([StageExecution("RESEARCHING", OK)])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="DONE"):
        project_pass_one([StageExecution(B, "DONE")])  # type: ignore[arg-type]


def test_projection_never_returns_a_state_outside_pass_one() -> None:
    allowed = {
        RunState.COLLECTING_BASELINE,
        RunState.BUSINESS_RESEARCH,
        RunState.COLLECTING_TARGETED,
        RunState.FAILED_COLLECTION,
        RunState.FAILED_RESEARCH,
    }
    for baseline in (None, *StageStatus):
        for research in (None, *StageStatus):
            with contextlib.suppress(InconsistentStageRecords):
                assert project_pass_one(records(baseline, research)) in allowed
