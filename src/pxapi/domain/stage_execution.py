"""Stage execution records and the Pass-1 projection onto the run state vocabulary.

PXAPI Confluence (Zielarchitektur §8) requires Baseline Website Measurements and Business
Context Research to run in parallel before the targeted pass. One top-level run state cannot
describe two concurrent activities; one execution record per stage can. This module holds the
stage vocabulary, the mapping from a failed stage to its coarse failure state, and **one** pure
function that projects the Pass-1 records onto the run state vocabulary.

Deliberately absent: a full stage lifecycle engine. From ``COLLECTING_TARGETED`` onwards the
run state machine in :mod:`pxapi.domain.run_state` is authoritative and stages are recorded,
not projected. The projection never requires records for stages that have not started.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from pxapi.domain.run_state import RunState


class Stage(StrEnum):
    """The processing activities of an Analysis Run, in canonical order."""

    BASELINE_COLLECTION = "BASELINE_COLLECTION"
    BUSINESS_RESEARCH = "BUSINESS_RESEARCH"
    TARGETED_COLLECTION = "TARGETED_COLLECTION"
    SYNTHESIS = "SYNTHESIS"
    SCORING = "SCORING"
    PRODUCT_DIAGNOSIS = "PRODUCT_DIAGNOSIS"
    CUSTOMER_PROJECTION = "CUSTOMER_PROJECTION"
    RENDERING = "RENDERING"
    VALIDATION = "VALIDATION"
    DELIVERY = "DELIVERY"


class StageStatus(StrEnum):
    """The execution status of one stage.

    ``CANCELLED`` is only ever the consequence of a concurrent sibling stage failing; it is
    never a state a stage enters on its own.
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


#: The two stages of Pass 1, which run concurrently after VERIFIED.
PASS_ONE_STAGES: frozenset[Stage] = frozenset({Stage.BASELINE_COLLECTION, Stage.BUSINESS_RESEARCH})

#: Which coarse failure state a failed stage produces. This is the precise failure indication
#: the run-state contract carries (``failure.failure_stage``): the top-level category stays
#: coarse, the stage says which activity failed. ``BLOCKED_INPUT`` has no stage: it happens
#: before any stage runs.
FAILURE_STATE_FOR: Mapping[Stage, RunState] = MappingProxyType(
    {
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
)


@dataclass(frozen=True)
class StageExecution:
    """A snapshot of one stage's current execution — not an attempt history."""

    stage: Stage
    status: StageStatus


class InconsistentStageRecords(ValueError):
    """The record set cannot describe a Pass-1 execution (duplicate, foreign or contradictory)."""


def project_pass_one(records: Iterable[StageExecution]) -> RunState:
    """Project the Pass-1 execution records onto the run state vocabulary.

    ``records`` holds at most one record per Pass-1 stage; a stage without a record has not
    started (``PENDING``). The result depends only on the record set, never on arrival order:

    * baseline ``FAILED`` → ``FAILED_COLLECTION`` (checked first: canonical stage order decides
      when both stages failed);
    * research ``FAILED`` → ``FAILED_RESEARCH``;
    * baseline not yet ``SUCCEEDED`` → ``COLLECTING_BASELINE`` (whatever research is doing);
    * baseline ``SUCCEEDED``, research not yet ``SUCCEEDED`` → ``BUSINESS_RESEARCH``;
    * both ``SUCCEEDED`` → ``COLLECTING_TARGETED``.

    Raises ``InconsistentStageRecords`` for a duplicate stage, a stage outside Pass 1 (the
    projection is not authoritative beyond Pass 1) or a ``CANCELLED`` record without a
    ``FAILED`` sibling (cancellation is only ever the consequence of a sibling failure).
    """
    status_of: dict[Stage, StageStatus] = {}
    for record in records:
        stage = Stage(record.stage)
        if stage not in PASS_ONE_STAGES:
            raise InconsistentStageRecords(f"stage outside Pass 1: {stage.value}")
        if stage in status_of:
            raise InconsistentStageRecords(f"duplicate record for stage {stage.value}")
        status_of[stage] = StageStatus(record.status)

    baseline = status_of.get(Stage.BASELINE_COLLECTION, StageStatus.PENDING)
    research = status_of.get(Stage.BUSINESS_RESEARCH, StageStatus.PENDING)
    statuses = (baseline, research)
    if StageStatus.CANCELLED in statuses and StageStatus.FAILED not in statuses:
        raise InconsistentStageRecords("a stage is CANCELLED but no sibling stage FAILED")

    if baseline is StageStatus.FAILED:
        return FAILURE_STATE_FOR[Stage.BASELINE_COLLECTION]
    if research is StageStatus.FAILED:
        return FAILURE_STATE_FOR[Stage.BUSINESS_RESEARCH]
    if baseline is not StageStatus.SUCCEEDED:
        return RunState.COLLECTING_BASELINE
    if research is not StageStatus.SUCCEEDED:
        return RunState.BUSINESS_RESEARCH
    return RunState.COLLECTING_TARGETED
