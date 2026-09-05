"""The global Analysis Run execution state and the approved transitions between states.

The vocabulary is deliberately coarse: ``CREATED -> QUEUED -> RUNNING -> SUCCEEDED | FAILED |
CANCELLED``. Business phases and provider outcomes are **not** run states. A stage's execution
is its own record with its own status vocabulary, and this module neither knows about stages
nor projects one onto the other in either direction.

The module is data plus one decision — is ``current -> target`` an approved edge? — and nothing
else. It reads no store, consults no clock, builds no ``problem`` document and carries no retry
policy. Every derived set is computed from ``ALLOWED_TRANSITIONS``, so the approved edge set
has exactly one place to be read from and cannot drift against a second copy.

``SUCCEEDED`` states only that execution finished without failing. It does **not** mean
customer release, delivery, report readiness, completed scoring, or that every stage succeeded;
those are other slices' facts and have no representation here.

Standard library only. The domain ring imports no third-party distribution at all.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType


class RunState(StrEnum):
    """The six global execution states of an Analysis Run, in lifecycle order."""

    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


#: The approved edge set — the single source of legality. Every state is a key, and a state
#: whose target set is empty is terminal. No pre-start cancellation, retry or reopen edge is
#: approved: adding one is a product decision, never an implementation convenience.
ALLOWED_TRANSITIONS: Mapping[RunState, frozenset[RunState]] = MappingProxyType(
    {
        RunState.CREATED: frozenset({RunState.QUEUED}),
        RunState.QUEUED: frozenset({RunState.RUNNING}),
        RunState.RUNNING: frozenset({RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED}),
        RunState.SUCCEEDED: frozenset(),
        RunState.FAILED: frozenset(),
        RunState.CANCELLED: frozenset(),
    }
)

#: Every approved ``(current, target)`` pair, derived from the mapping above.
LEGAL_TRANSITIONS: frozenset[tuple[RunState, RunState]] = frozenset(
    (current, target) for current, targets in ALLOWED_TRANSITIONS.items() for target in targets
)

#: The states with no outgoing approved edge, derived from the mapping above.
TERMINAL_STATES: frozenset[RunState] = frozenset(
    state for state, targets in ALLOWED_TRANSITIONS.items() if not targets
)


class IllegalTransition(Exception):
    """``current -> target`` is not an approved edge of the accepted lifecycle.

    ``code`` is the registered problem code for this category. ``str()`` names the two states
    and nothing else, so the message carries no run identity and no execution detail.
    """

    code = "ILLEGAL_RUN_TRANSITION"

    def __init__(self, current: RunState, target: RunState) -> None:
        super().__init__(f"illegal run transition: {current.value} -> {target.value}")
        self.current = current
        self.target = target


def is_terminal(state: RunState) -> bool:
    """Whether ``state`` has no outgoing approved edge. Raises on an unknown token."""
    return RunState(state) in TERMINAL_STATES


def can_transition(current: RunState, target: RunState) -> bool:
    """Whether ``current -> target`` is approved. Raises on an unknown token."""
    return RunState(target) in ALLOWED_TRANSITIONS[RunState(current)]


def transition(current: RunState, target: RunState) -> RunState:
    """Return ``target`` when ``current -> target`` is approved, else raise ``IllegalTransition``.

    Both arguments are resolved through ``RunState`` first, so an unknown token is a ``ValueError``
    about the vocabulary rather than a transition verdict about a state that does not exist.
    """
    current = RunState(current)
    target = RunState(target)
    if target not in ALLOWED_TRANSITIONS[current]:
        raise IllegalTransition(current, target)
    return target
