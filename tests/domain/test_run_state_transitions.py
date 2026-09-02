"""AC4: legal and illegal Analysis Run transitions, derived from the state set and edge set.

``APPROVED_EDGES`` below is the approved edge list written out as literal data, independent
of the module under test; the module's mapping must equal it exactly. Every count is derived
by enumeration (19 states -> 361 ordered pairs -> 27 legal, 334 illegal), never hardcoded as a
source of truth — the literal numbers appear only as a cross-check of the derivation.
"""

from __future__ import annotations

from itertools import product

import pytest

from pxapi.domain.run_state import (
    ALLOWED_TRANSITIONS,
    FAILURE_STATES,
    LEGAL_TRANSITIONS,
    SUCCESS_PATH,
    TERMINAL_STATES,
    IllegalTransition,
    RunState,
    can_transition,
    is_failure,
    is_terminal,
    transition,
)

S = RunState

#: The approved edges, verbatim from the A4 implementation prompt (Confluence §16 vocabulary).
APPROVED_EDGES: frozenset[tuple[RunState, RunState]] = frozenset(
    {
        (S.REQUESTED, S.VERIFIED),
        (S.REQUESTED, S.BLOCKED_INPUT),
        (S.VERIFIED, S.COLLECTING_BASELINE),
        (S.VERIFIED, S.BLOCKED_INPUT),
        (S.COLLECTING_BASELINE, S.BUSINESS_RESEARCH),
        (S.COLLECTING_BASELINE, S.COLLECTING_TARGETED),
        (S.COLLECTING_BASELINE, S.FAILED_COLLECTION),
        (S.COLLECTING_BASELINE, S.FAILED_RESEARCH),
        (S.BUSINESS_RESEARCH, S.COLLECTING_TARGETED),
        (S.BUSINESS_RESEARCH, S.FAILED_RESEARCH),
        (S.COLLECTING_TARGETED, S.SYNTHESIZING),
        (S.COLLECTING_TARGETED, S.FAILED_COLLECTION),
        (S.SYNTHESIZING, S.SCORING),
        (S.SYNTHESIZING, S.FAILED_SYNTHESIS),
        (S.SCORING, S.PRODUCT_DIAGNOSIS),
        (S.SCORING, S.FAILED_SYNTHESIS),
        (S.PRODUCT_DIAGNOSIS, S.CUSTOMER_PROJECTING),
        (S.PRODUCT_DIAGNOSIS, S.FAILED_SYNTHESIS),
        (S.CUSTOMER_PROJECTING, S.RENDERING),
        (S.CUSTOMER_PROJECTING, S.FAILED_SYNTHESIS),
        (S.RENDERING, S.VALIDATING),
        (S.RENDERING, S.FAILED_VALIDATION),
        (S.VALIDATING, S.READY),
        (S.VALIDATING, S.FAILED_VALIDATION),
        (S.READY, S.DELIVERED),
        (S.READY, S.DELIVERY_FAILED),
        (S.DELIVERY_FAILED, S.READY),
    }
)

ALL_PAIRS: frozenset[tuple[RunState, RunState]] = frozenset(product(RunState, RunState))
ILLEGAL_PAIRS: frozenset[tuple[RunState, RunState]] = ALL_PAIRS - APPROVED_EDGES


def _pair_id(pair: tuple[RunState, RunState]) -> str:
    return f"{pair[0].value}->{pair[1].value}"


# --- vocabulary ---------------------------------------------------------------------------------


def test_vocabulary_is_exactly_the_nineteen_confluence_states() -> None:
    assert [s.value for s in SUCCESS_PATH] == [
        "REQUESTED",
        "VERIFIED",
        "COLLECTING_BASELINE",
        "BUSINESS_RESEARCH",
        "COLLECTING_TARGETED",
        "SYNTHESIZING",
        "SCORING",
        "PRODUCT_DIAGNOSIS",
        "CUSTOMER_PROJECTING",
        "RENDERING",
        "VALIDATING",
        "READY",
        "DELIVERED",
    ]
    assert {s.value for s in FAILURE_STATES} == {
        "BLOCKED_INPUT",
        "FAILED_COLLECTION",
        "FAILED_RESEARCH",
        "FAILED_SYNTHESIS",
        "FAILED_VALIDATION",
        "DELIVERY_FAILED",
    }
    assert set(SUCCESS_PATH) | FAILURE_STATES == set(RunState)
    assert not set(SUCCESS_PATH) & FAILURE_STATES
    assert len(RunState) == 19


# --- the edge set is the approved one, and the counts derive from it ---------------------------


def test_module_edge_set_equals_the_approved_edges_exactly() -> None:
    assert LEGAL_TRANSITIONS == APPROVED_EDGES
    assert set(ALLOWED_TRANSITIONS) == set(RunState), "every state must be a key"


def test_derived_counts() -> None:
    assert len(ALL_PAIRS) == len(RunState) ** 2
    assert len(ALL_PAIRS) == 361
    assert len(APPROVED_EDGES) == 27
    assert len(ILLEGAL_PAIRS) == len(ALL_PAIRS) - len(APPROVED_EDGES) == 334
    self_loops = {pair for pair in ILLEGAL_PAIRS if pair[0] is pair[1]}
    assert len(self_loops) == 19, "no state may transition to itself"


# --- M: every approved transition succeeds ------------------------------------------------------


@pytest.mark.parametrize("pair", sorted(APPROVED_EDGES), ids=_pair_id)
def test_approved_transition_succeeds(pair: tuple[RunState, RunState]) -> None:
    current, target = pair
    assert can_transition(current, target) is True
    assert transition(current, target) is target


# --- N: every other ordered pair fails ----------------------------------------------------------


@pytest.mark.parametrize("pair", sorted(ILLEGAL_PAIRS), ids=_pair_id)
def test_every_other_ordered_pair_is_illegal(pair: tuple[RunState, RunState]) -> None:
    current, target = pair
    assert can_transition(current, target) is False
    with pytest.raises(IllegalTransition) as info:
        transition(current, target)
    assert info.value.current is current
    assert info.value.target is target
    assert info.value.code == "ILLEGAL_RUN_TRANSITION"


def test_illegal_transition_message_names_only_the_two_states() -> None:
    message = str(IllegalTransition(S.FAILED_SYNTHESIS, S.READY))
    assert message == "illegal run transition: FAILED_SYNTHESIS -> READY"


def test_unknown_state_strings_are_rejected_before_any_transition_decision() -> None:
    with pytest.raises(ValueError, match="DONE"):
        transition("READY", "DONE")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="done"):
        transition("done", S.READY)  # type: ignore[arg-type]


def test_state_values_are_accepted_as_plain_strings() -> None:
    assert transition("REQUESTED", "VERIFIED") is S.VERIFIED  # type: ignore[arg-type]


# --- O: terminal-state rules -------------------------------------------------------------------


def test_terminal_states_are_exactly_those_without_an_outgoing_approved_edge() -> None:
    derived = {state for state in RunState if not any(c is state for c, _ in APPROVED_EDGES)}
    assert derived == TERMINAL_STATES
    assert derived == {
        S.DELIVERED,
        S.BLOCKED_INPUT,
        S.FAILED_COLLECTION,
        S.FAILED_RESEARCH,
        S.FAILED_SYNTHESIS,
        S.FAILED_VALIDATION,
    }


@pytest.mark.parametrize("state", sorted(RunState, key=lambda s: s.value))
def test_terminal_predicate_matches_the_edge_set(state: RunState) -> None:
    assert is_terminal(state) == (state in TERMINAL_STATES)
    assert is_failure(state) == (state in FAILURE_STATES)
    if is_terminal(state):
        for target in RunState:
            assert not can_transition(state, target)


def test_delivery_failed_is_the_only_non_terminal_failure_state() -> None:
    assert {S.DELIVERY_FAILED} == FAILURE_STATES - TERMINAL_STATES
    assert ALLOWED_TRANSITIONS[S.DELIVERY_FAILED] == {S.READY}


def test_every_failure_state_is_reachable() -> None:
    for state in FAILURE_STATES:
        assert any(target is state for _, target in APPROVED_EDGES), state


# --- P: no failure state except DELIVERY_FAILED can reach READY --------------------------------


def test_ready_is_entered_only_from_validating_and_delivery_failed() -> None:
    incoming = {current for current, target in APPROVED_EDGES if target is S.READY}
    assert incoming == {S.VALIDATING, S.DELIVERY_FAILED}


@pytest.mark.parametrize(
    "state", sorted(FAILURE_STATES - {S.DELIVERY_FAILED}, key=lambda s: s.value)
)
def test_no_other_failure_state_reaches_ready_or_delivered(state: RunState) -> None:
    assert not can_transition(state, S.READY)
    assert not can_transition(state, S.DELIVERED)
    assert not any(current is state for current, _ in APPROVED_EDGES)


def test_delivered_is_entered_only_from_ready_and_is_final() -> None:
    incoming = {current for current, target in APPROVED_EDGES if target is S.DELIVERED}
    assert incoming == {S.READY}
    assert not can_transition(S.VALIDATING, S.DELIVERED)
    assert not can_transition(S.DELIVERED, S.READY)
    assert transition(S.READY, S.DELIVERED) is S.DELIVERED


def test_delivery_retry_cycle_is_the_only_cycle() -> None:
    """READY -> DELIVERY_FAILED -> READY may repeat; nothing else in the graph loops."""
    assert transition(transition(S.READY, S.DELIVERY_FAILED), S.READY) is S.READY
    reachable_back: set[tuple[RunState, RunState]] = set()
    for a, b in APPROVED_EDGES:
        if (b, a) in APPROVED_EDGES:
            reachable_back.add((a, b))
    assert reachable_back == {(S.READY, S.DELIVERY_FAILED), (S.DELIVERY_FAILED, S.READY)}


def test_success_path_is_walkable_edge_by_edge() -> None:
    state = SUCCESS_PATH[0]
    for target in SUCCESS_PATH[1:]:
        state = transition(state, target)
    assert state is S.DELIVERED
