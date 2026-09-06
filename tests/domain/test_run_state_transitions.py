"""Every ordered pair of the six global run states, decided one way or the other.

The expected vocabulary and the expected edge set are written here as literal strings. They
are deliberately *not* imported from the module under test: a test that read its expectation
from the implementation would agree with any implementation, including a wrong one. Only the
``RunState`` type itself is imported, and every assertion compares it against the literals.

The counts are cross-checked two ways — enumerated from the vocabulary and stated as literals —
so a vocabulary that silently grew cannot leave the arithmetic self-consistent.
"""

from __future__ import annotations

from itertools import product

import pytest

from pxapi.domain.run_state import (
    ALLOWED_TRANSITIONS,
    LEGAL_TRANSITIONS,
    TERMINAL_STATES,
    IllegalTransition,
    RunState,
    can_transition,
    is_terminal,
    transition,
)

#: The approved global execution vocabulary, in lifecycle order. Six values, no seventh.
APPROVED_STATES: tuple[str, ...] = (
    "CREATED",
    "QUEUED",
    "RUNNING",
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
)

#: The approved edge set: CREATED -> QUEUED -> RUNNING -> SUCCEEDED | FAILED | CANCELLED.
#: No pre-start cancellation, no retry, no reopen, no outgoing edge from a terminal state.
APPROVED_EDGE_NAMES: frozenset[tuple[str, str]] = frozenset(
    {
        ("CREATED", "QUEUED"),
        ("QUEUED", "RUNNING"),
        ("RUNNING", "SUCCEEDED"),
        ("RUNNING", "FAILED"),
        ("RUNNING", "CANCELLED"),
    }
)

#: The states with no outgoing approved edge, stated as literals and re-derived below.
APPROVED_TERMINAL_NAMES: frozenset[str] = frozenset({"SUCCEEDED", "FAILED", "CANCELLED"})

#: Every state name PR #5 used as a *global* run state. None may re-enter this vocabulary:
#: a stage, a business phase and a delivery outcome are not global execution states.
PR5_STATE_NAMES: tuple[str, ...] = (
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
    "BLOCKED_INPUT",
    "FAILED_COLLECTION",
    "FAILED_RESEARCH",
    "FAILED_SYNTHESIS",
    "FAILED_VALIDATION",
    "DELIVERY_FAILED",
)

ALL_PAIR_NAMES: frozenset[tuple[str, str]] = frozenset(product(APPROVED_STATES, APPROVED_STATES))
ILLEGAL_PAIR_NAMES: frozenset[tuple[str, str]] = ALL_PAIR_NAMES - APPROVED_EDGE_NAMES


def _pair_id(pair: tuple[str, str]) -> str:
    return f"{pair[0]}->{pair[1]}"


# --- the vocabulary ------------------------------------------------------------------------


def test_the_vocabulary_is_exactly_the_six_approved_states_in_order() -> None:
    assert [state.value for state in RunState] == list(APPROVED_STATES)
    assert len(RunState) == 6


@pytest.mark.parametrize("name", APPROVED_STATES)
def test_each_approved_state_resolves_from_its_own_token(name: str) -> None:
    assert RunState(name).value == name


@pytest.mark.parametrize("name", PR5_STATE_NAMES)
def test_no_pr5_state_name_is_a_global_run_state(name: str) -> None:
    """Regression against the 19-state model: a stage or business phase is not a run state."""
    assert name not in {state.value for state in RunState}
    with pytest.raises(ValueError, match=name):
        RunState(name)


# --- the edge set --------------------------------------------------------------------------


def test_the_module_edge_set_equals_the_approved_edges_exactly() -> None:
    derived = {(current.value, target.value) for current, target in LEGAL_TRANSITIONS}
    assert derived == set(APPROVED_EDGE_NAMES)


def test_every_state_is_a_key_of_the_transition_mapping() -> None:
    assert {state.value for state in ALLOWED_TRANSITIONS} == set(APPROVED_STATES)


def test_the_pair_counts_are_five_legal_and_thirty_one_illegal() -> None:
    assert len(ALL_PAIR_NAMES) == len(APPROVED_STATES) ** 2 == 36
    assert len(APPROVED_EDGE_NAMES) == 5
    assert len(ILLEGAL_PAIR_NAMES) == 31
    self_pairs = {pair for pair in ILLEGAL_PAIR_NAMES if pair[0] == pair[1]}
    assert len(self_pairs) == 6, "every self-transition must be illegal"


@pytest.mark.parametrize("pair", sorted(APPROVED_EDGE_NAMES), ids=_pair_id)
def test_an_approved_transition_succeeds(pair: tuple[str, str]) -> None:
    current, target = RunState(pair[0]), RunState(pair[1])
    assert can_transition(current, target) is True
    assert transition(current, target) is target


@pytest.mark.parametrize("pair", sorted(ILLEGAL_PAIR_NAMES), ids=_pair_id)
def test_every_other_ordered_pair_is_illegal(pair: tuple[str, str]) -> None:
    current, target = RunState(pair[0]), RunState(pair[1])
    assert can_transition(current, target) is False
    with pytest.raises(IllegalTransition) as info:
        transition(current, target)
    assert info.value.current is current
    assert info.value.target is target
    assert info.value.code == "ILLEGAL_RUN_TRANSITION"


@pytest.mark.parametrize("pair", sorted(ILLEGAL_PAIR_NAMES), ids=_pair_id)
def test_an_illegal_transition_is_refused_deterministically(pair: tuple[str, str]) -> None:
    """The same pair is refused the same way twice; no counter, clock or store is consulted."""
    current, target = RunState(pair[0]), RunState(pair[1])
    first = [can_transition(current, target) for _ in range(3)]
    assert first == [False, False, False]


# --- terminality is derived, not declared ----------------------------------------------------


def test_terminal_states_are_exactly_the_states_with_no_outgoing_approved_edge() -> None:
    derived = {
        name for name in APPROVED_STATES if not any(c == name for c, _ in APPROVED_EDGE_NAMES)
    }
    assert derived == set(APPROVED_TERMINAL_NAMES)
    assert {state.value for state in TERMINAL_STATES} == set(APPROVED_TERMINAL_NAMES)


@pytest.mark.parametrize("name", APPROVED_STATES)
def test_a_terminal_state_has_no_outgoing_edge_at_all(name: str) -> None:
    state = RunState(name)
    assert is_terminal(state) is (name in APPROVED_TERMINAL_NAMES)
    if is_terminal(state):
        assert not any(can_transition(state, target) for target in RunState)


# --- walking the lifecycle -------------------------------------------------------------------


@pytest.mark.parametrize("outcome", sorted(APPROVED_TERMINAL_NAMES))
def test_each_terminal_outcome_is_reachable_edge_by_edge_from_created(outcome: str) -> None:
    state = RunState.CREATED
    for target in ("QUEUED", "RUNNING", outcome):
        state = transition(state, RunState(target))
    assert state is RunState(outcome)
    assert is_terminal(state)


def test_the_illegal_transition_message_names_only_the_two_states() -> None:
    """No run id, no stage, no store detail: the message is safe to surface as it stands."""
    error = IllegalTransition(RunState.SUCCEEDED, RunState.RUNNING)
    assert str(error) == "illegal run transition: SUCCEEDED -> RUNNING"


def test_an_unknown_state_token_is_rejected_before_any_transition_decision() -> None:
    with pytest.raises(ValueError, match="READY"):
        transition("RUNNING", "READY")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="running"):
        transition("running", RunState.SUCCEEDED)  # type: ignore[arg-type]


def test_a_state_token_is_accepted_wherever_a_state_is() -> None:
    assert transition("CREATED", "QUEUED") is RunState.QUEUED  # type: ignore[arg-type]
    assert is_terminal("FAILED") is True  # type: ignore[arg-type]
    assert can_transition("QUEUED", "RUNNING") is True  # type: ignore[arg-type]
