from __future__ import annotations

import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from scenarios.schemas import ScenarioExecutionRequest


class ScheduledEventType(StrEnum):
    AUTHORIZATION = "authorization"
    SETTLEMENT = "settlement"
    REVERSAL = "reversal"
    CUSTOMER_ACTION = "customer_action"
    OUTCOME_PERSISTENCE = "outcome_persistence"


class EnqueueScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_request: ScenarioExecutionRequest
    start_at: datetime.datetime | None = None
    end_at: datetime.datetime | None = Field(
        None,
        description="Optional schedule cutoff; events after this time are not persisted or queued.",
    )
    schedule_id: str | None = Field(None, max_length=128)
    dispatch_transport: str | None = Field(
        None,
        description="Override dispatch transport: cloud_tasks, inline, or record_only.",
    )


class ScheduledEventRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    schedule_id: str
    scenario_id: str | None = None
    execution_id: str | None = None
    event_id: str
    parent_event_id: str | None = None
    event_type: ScheduledEventType | str
    persona_id: str | None = None
    status: str
    idempotency_key: str
    scheduled_for: datetime.datetime
    payload: dict[str, Any] = Field(default_factory=dict)
    result_payload: dict[str, Any] = Field(default_factory=dict)
    attempts: int = 0
    last_error: str | None = None


class SchedulePlanResult(BaseModel):
    schedule_id: str
    scenario_id: str | None = None
    execution_id: str | None = None
    created_events: list[ScheduledEventRecord] = Field(default_factory=list)
    dispatch_transport: str
    cloud_tasks_enqueued: int = 0
    warnings: list[str] = Field(default_factory=list)


class ScheduledEventDispatchResult(BaseModel):
    event_record_id: str
    schedule_id: str
    event_id: str
    event_type: str
    status: str
    message: str
    result_payload: dict[str, Any] = Field(default_factory=dict)
