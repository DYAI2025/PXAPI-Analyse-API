"""What the multi-page orchestration emits for each way a run can end (PXAPI-25).

The contracts deliberately leave this open. ``analysis-run-state`` and ``stage-execution-record``
are linked by ``run_id`` alone, a ``FAILED`` stage beside a ``SUCCEEDED`` run is contract-valid,
and ``contracts/README.md`` states that whether a stage failure is fatal to a run is
*orchestration policy, which no contract decides*. The multi-page path has decided it, in code:
``DiscoverSite`` followed by ``AcquireSelectedPages`` fails the run whenever a stage fails, and
emits exactly one stage history and one set of members per outcome. This module states that
decision once, so run validation can hold a run to the lifecycle its producer actually has
rather than to the looser one its schemas permit.

It is a statement *about* those producers, not a second state machine: the run-state edges stay
in ``pxapi.domain.run_state``, every stage token and failure code is imported from the module
that emits it, and ``tests/application/test_validation_binding_and_lifecycle.py`` runs every
genuine producer path and requires each to satisfy this table — the table cannot drift from the
producer without a test going red.

Two limits are deliberate. No producer of this slice emits ``CANCELLED``, so no stage history
is stated for it; the one thing known about it is the one thing known about every run that did
not succeed — it carries no page documents, because ``AcquireSelectedPages`` only ever emits
them on its ``SUCCEEDED`` return. And a failure code this table does not know is left to the
validator's own ``RUN_FAILURE_UNCLASSIFIED``, never guessed at here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from pxapi.application.acquire_selected_pages import (
    ACQUISITION_WITHHELD_CODE,
    PAGE_ACQUISITION_STAGE,
    PAGE_DOCUMENT_MEMBERS,
    SELECTION_NOT_ADMISSIBLE_CODE,
)
from pxapi.application.discover_site import (
    BOOTSTRAP_FAILURE_CODE,
    INVENTORY_WITHHELD_CODE,
    MANIFEST_WITHHELD_CODE,
    TARGET_NOT_PERMITTED_CODE,
    UNEXPLAINED_BOOTSTRAP_CODE,
)
from pxapi.domain.acquisition_semantics import SemanticViolation
from pxapi.domain.run_state import RunState
from pxapi.domain.site_discovery import DiscoveryStage

#: The stable names of the two rules, as a receipt reason carries them.
STAGE_HISTORY_RULE: Final = "stage_history_follows_run_outcome"
MEMBER_RULE: Final = "member_follows_run_outcome"

_SUCCEEDED: Final = RunState.SUCCEEDED.value
_FAILED: Final = RunState.FAILED.value
_DISCOVERY: Final = DiscoveryStage.SITE_DISCOVERY.value
_PLAN: Final = DiscoveryStage.SAMPLING_PLAN.value

#: The members every run of this orchestration carries, whatever became of it.
_ALWAYS: Final = frozenset({"analysis_run_request", "analysis_run_state", "stage_executions"})


@dataclass(frozen=True)
class Lifecycle:
    """One outcome: the ordered ``(stage_id, status)`` history and the members it emits."""

    stages: tuple[tuple[str, str], ...]
    members: frozenset[str]
    #: Members the outcome may or may not carry. Only the refused target has one: a target
    #: refused for carrying credentials withholds its request (data minimisation), a target
    #: refused for any other reason does not.
    optional: frozenset[str] = frozenset()


_DISCOVERY_FAILED: Final = Lifecycle(((_DISCOVERY, _FAILED),), _ALWAYS)
_ACQUISITION_FAILED: Final = (
    (_DISCOVERY, _SUCCEEDED),
    (_PLAN, _SUCCEEDED),
    (PAGE_ACQUISITION_STAGE, _FAILED),
)

#: ``(run state, failure code) -> Lifecycle``, for every outcome the orchestration can end in.
LIFECYCLES: Final[dict[tuple[str, str | None], Lifecycle]] = {
    (_SUCCEEDED, None): Lifecycle(
        ((_DISCOVERY, _SUCCEEDED), (_PLAN, _SUCCEEDED), (PAGE_ACQUISITION_STAGE, _SUCCEEDED)),
        _ALWAYS | {"site_inventory", "sampling_manifest", *PAGE_DOCUMENT_MEMBERS},
    ),
    **{
        (_FAILED, code): _DISCOVERY_FAILED
        for code in (
            *BOOTSTRAP_FAILURE_CODE.values(),
            UNEXPLAINED_BOOTSTRAP_CODE,
            INVENTORY_WITHHELD_CODE,
        )
        if code != TARGET_NOT_PERMITTED_CODE
    },
    (_FAILED, TARGET_NOT_PERMITTED_CODE): Lifecycle(
        ((_DISCOVERY, _FAILED),),
        _ALWAYS - {"analysis_run_request"},
        optional=frozenset({"analysis_run_request"}),
    ),
    (_FAILED, MANIFEST_WITHHELD_CODE): Lifecycle(
        ((_DISCOVERY, _SUCCEEDED), (_PLAN, _FAILED)), _ALWAYS | {"site_inventory"}
    ),
    (_FAILED, SELECTION_NOT_ADMISSIBLE_CODE): Lifecycle(
        _ACQUISITION_FAILED, _ALWAYS | {"site_inventory"}
    ),
    (_FAILED, ACQUISITION_WITHHELD_CODE): Lifecycle(
        _ACQUISITION_FAILED, _ALWAYS | {"site_inventory", "sampling_manifest"}
    ),
}

#: Every member a run of this orchestration can carry: the succeeded run carries them all.
CANONICAL_MEMBER_NAMES: Final = LIFECYCLES[(_SUCCEEDED, None)].members


def _outcome(envelope: Mapping[str, Any]) -> tuple[str | None, str | None]:
    state = envelope.get("analysis_run_state")
    if not isinstance(state, dict):
        return None, None
    failure = state.get("failure")
    code = failure.get("code") if isinstance(failure, dict) else None
    value = state.get("state")
    return (value if isinstance(value, str) else None), (code if isinstance(code, str) else None)


def _history(value: Any) -> list[tuple[Any, Any]] | None:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        return None
    return [(item.get("stage_id"), item.get("status")) for item in value]


def lifecycle_violations(envelope: Mapping[str, Any]) -> tuple[SemanticViolation, ...]:
    """Where the run's stage history or members contradict how the run ended. Never raises.

    Only canonical members are judged: a member no run of this analysis emits is the
    validator's ``CANONICAL_MEMBER_UNEXPECTED``, not a lifecycle question.
    """
    state, code = _outcome(envelope)
    if state is None:
        return ()
    found: list[SemanticViolation] = []

    if state != _SUCCEEDED:
        # The one fact that holds for every run that did not succeed, CANCELLED included.
        found.extend(
            SemanticViolation(f"/{name}", MEMBER_RULE)
            for name in PAGE_DOCUMENT_MEMBERS
            if name in envelope
        )

    lifecycle = LIFECYCLES.get((state, code if state == _FAILED else None))
    if lifecycle is None:
        return tuple(found)

    history = _history(envelope.get("stage_executions"))
    if history is not None and history != list(lifecycle.stages):
        found.append(SemanticViolation("/stage_executions", STAGE_HISTORY_RULE))

    allowed = lifecycle.members | lifecycle.optional
    for name in sorted(CANONICAL_MEMBER_NAMES - set(PAGE_DOCUMENT_MEMBERS)):
        present = name in envelope
        if (present and name not in allowed) or (not present and name in lifecycle.members):
            found.append(SemanticViolation(f"/{name}", MEMBER_RULE))
    return tuple(found)
