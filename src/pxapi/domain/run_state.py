"""Analysis Run state vocabulary and the approved transitions between states.

The vocabulary and the edges are the ones fixed in PXAPI Confluence (Zielarchitektur §16) and
approved for slice A4. This module is data plus one decision — is ``current -> target`` an
approved edge? — and nothing else: it inspects no stores, knows no gates, builds no problem
documents and carries no retry policy. Every derived set (``LEGAL_TRANSITIONS``,
``TERMINAL_STATES``) is computed from ``ALLOWED_TRANSITIONS``, so there is exactly one place to
read the edge set from.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType


class RunState(StrEnum):
    """The nineteen Analysis Run states: thirteen lifecycle states, six explicit failures."""

    REQUESTED = "REQUESTED"
    VERIFIED = "VERIFIED"
    COLLECTING_BASELINE = "COLLECTING_BASELINE"
    BUSINESS_RESEARCH = "BUSINESS_RESEARCH"
    COLLECTING_TARGETED = "COLLECTING_TARGETED"
    SYNTHESIZING = "SYNTHESIZING"
    SCORING = "SCORING"
    PRODUCT_DIAGNOSIS = "PRODUCT_DIAGNOSIS"
    CUSTOMER_PROJECTING = "CUSTOMER_PROJECTING"
    RENDERING = "RENDERING"
    VALIDATING = "VALIDATING"
    READY = "READY"
    DELIVERED = "DELIVERED"

    BLOCKED_INPUT = "BLOCKED_INPUT"
    FAILED_COLLECTION = "FAILED_COLLECTION"
    FAILED_RESEARCH = "FAILED_RESEARCH"
    FAILED_SYNTHESIS = "FAILED_SYNTHESIS"
    FAILED_VALIDATION = "FAILED_VALIDATION"
    DELIVERY_FAILED = "DELIVERY_FAILED"


#: The lifecycle states in canonical order (Confluence §16).
SUCCESS_PATH: tuple[RunState, ...] = (
    RunState.REQUESTED,
    RunState.VERIFIED,
    RunState.COLLECTING_BASELINE,
    RunState.BUSINESS_RESEARCH,
    RunState.COLLECTING_TARGETED,
    RunState.SYNTHESIZING,
    RunState.SCORING,
    RunState.PRODUCT_DIAGNOSIS,
    RunState.CUSTOMER_PROJECTING,
    RunState.RENDERING,
    RunState.VALIDATING,
    RunState.READY,
    RunState.DELIVERED,
)

#: The explicit failure states. None of them is ever converted to READY silently; the only
#: failure state with an outgoing edge at all is DELIVERY_FAILED (delivery may be retried
#: without recomputing the analysis).
FAILURE_STATES: frozenset[RunState] = frozenset(
    {
        RunState.BLOCKED_INPUT,
        RunState.FAILED_COLLECTION,
        RunState.FAILED_RESEARCH,
        RunState.FAILED_SYNTHESIS,
        RunState.FAILED_VALIDATION,
        RunState.DELIVERY_FAILED,
    }
)

#: The approved edge set — the single source of truth for legality. Every state is a key;
#: a state with an empty target set is terminal.
ALLOWED_TRANSITIONS: Mapping[RunState, frozenset[RunState]] = MappingProxyType(
    {
        RunState.REQUESTED: frozenset({RunState.VERIFIED, RunState.BLOCKED_INPUT}),
        RunState.VERIFIED: frozenset({RunState.COLLECTING_BASELINE, RunState.BLOCKED_INPUT}),
        # Pass 1: baseline collection and business research run concurrently. Research may
        # finish first (then baseline completion goes straight to COLLECTING_TARGETED), and
        # research may fail while baseline is still running.
        RunState.COLLECTING_BASELINE: frozenset(
            {
                RunState.BUSINESS_RESEARCH,
                RunState.COLLECTING_TARGETED,
                RunState.FAILED_COLLECTION,
                RunState.FAILED_RESEARCH,
            }
        ),
        RunState.BUSINESS_RESEARCH: frozenset(
            {RunState.COLLECTING_TARGETED, RunState.FAILED_RESEARCH}
        ),
        RunState.COLLECTING_TARGETED: frozenset(
            {RunState.SYNTHESIZING, RunState.FAILED_COLLECTION}
        ),
        RunState.SYNTHESIZING: frozenset({RunState.SCORING, RunState.FAILED_SYNTHESIS}),
        RunState.SCORING: frozenset({RunState.PRODUCT_DIAGNOSIS, RunState.FAILED_SYNTHESIS}),
        RunState.PRODUCT_DIAGNOSIS: frozenset(
            {RunState.CUSTOMER_PROJECTING, RunState.FAILED_SYNTHESIS}
        ),
        RunState.CUSTOMER_PROJECTING: frozenset({RunState.RENDERING, RunState.FAILED_SYNTHESIS}),
        RunState.RENDERING: frozenset({RunState.VALIDATING, RunState.FAILED_VALIDATION}),
        # VALIDATING -> READY means the caller reports that its required validations
        # succeeded; the domain inspects no gate.
        RunState.VALIDATING: frozenset({RunState.READY, RunState.FAILED_VALIDATION}),
        # READY -> DELIVERED means a delivery action was reported successful; READY is also a
        # permitted resting state for a run that requested no delivery.
        RunState.READY: frozenset({RunState.DELIVERED, RunState.DELIVERY_FAILED}),
        RunState.DELIVERED: frozenset(),
        RunState.BLOCKED_INPUT: frozenset(),
        RunState.FAILED_COLLECTION: frozenset(),
        RunState.FAILED_RESEARCH: frozenset(),
        RunState.FAILED_SYNTHESIS: frozenset(),
        RunState.FAILED_VALIDATION: frozenset(),
        # The sole recovery edge: a delivery may be retried without recomputing the analysis.
        RunState.DELIVERY_FAILED: frozenset({RunState.READY}),
    }
)

#: Every approved ``(current, target)`` pair, derived from the mapping above.
LEGAL_TRANSITIONS: frozenset[tuple[RunState, RunState]] = frozenset(
    (current, target) for current, targets in ALLOWED_TRANSITIONS.items() for target in targets
)

#: States with no outgoing edge, derived from the mapping above.
TERMINAL_STATES: frozenset[RunState] = frozenset(
    state for state, targets in ALLOWED_TRANSITIONS.items() if not targets
)


class IllegalTransition(Exception):
    """``current -> target`` is not an approved edge.

    ``code`` is the registered problem code for this category. ``str()`` names only the two
    states, so the message is safe to surface to a client as it is.
    """

    code = "ILLEGAL_RUN_TRANSITION"

    def __init__(self, current: RunState, target: RunState) -> None:
        super().__init__(f"illegal run transition: {current.value} -> {target.value}")
        self.current = current
        self.target = target


def is_terminal(state: RunState) -> bool:
    return RunState(state) in TERMINAL_STATES


def is_failure(state: RunState) -> bool:
    return RunState(state) in FAILURE_STATES


def can_transition(current: RunState, target: RunState) -> bool:
    return RunState(target) in ALLOWED_TRANSITIONS[RunState(current)]


def transition(current: RunState, target: RunState) -> RunState:
    """Return ``target`` if ``current -> target`` is approved, else raise ``IllegalTransition``."""
    current = RunState(current)
    target = RunState(target)
    if target not in ALLOWED_TRANSITIONS[current]:
        raise IllegalTransition(current, target)
    return target
