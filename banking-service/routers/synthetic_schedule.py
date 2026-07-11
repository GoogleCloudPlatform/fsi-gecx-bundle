import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from services.synthetic_schedule import SyntheticScheduleService
from utils.database import get_db
from utils.internal_execution import require_internal_simulation_context
from utils.maintenance import ensure_system_writable

router = APIRouter(
    prefix="/api/v1/synthetic-schedule",
    tags=["Synthetic Schedule"],
    dependencies=[Depends(require_internal_simulation_context)],
)


class SyntheticScheduledEventCreateRequest(BaseModel):
    schedule_id: str = Field(..., min_length=1, max_length=128)
    scenario_id: str | None = Field(None, max_length=128)
    execution_id: str | None = Field(None, max_length=128)
    event_id: str = Field(..., min_length=1, max_length=128)
    parent_event_id: str | None = Field(None, max_length=128)
    event_type: str = Field(..., min_length=1, max_length=64)
    persona_id: str | None = Field(None, max_length=128)
    scheduled_for: datetime.datetime
    idempotency_key: str = Field(..., min_length=8, max_length=200)
    payload: dict = Field(default_factory=dict)


class SyntheticScheduledEventUpdateRequest(BaseModel):
    result_payload: dict = Field(default_factory=dict)
    error: str | None = Field(None, max_length=1024)


@router.post("/events", status_code=status.HTTP_201_CREATED)
def create_scheduled_event(
    request: SyntheticScheduledEventCreateRequest,
    db: Session = Depends(get_db),
):
    ensure_system_writable("synthetic scheduled event create")
    return SyntheticScheduleService(db).create_event(**request.model_dump())


@router.get("/events", status_code=status.HTTP_200_OK)
def list_scheduled_events(
    schedule_id: str | None = None,
    status_filter: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    return SyntheticScheduleService(db).list_events(
        schedule_id=schedule_id,
        status=status_filter,
        limit=max(1, min(limit, 500)),
    )


@router.get("/events/{event_record_id}", status_code=status.HTTP_200_OK)
def get_scheduled_event(event_record_id: str, db: Session = Depends(get_db)):
    event = SyntheticScheduleService(db).get_event(event_record_id)
    if not event:
        raise HTTPException(status_code=404, detail="Scheduled event not found.")
    return event


@router.get("/schedules/{schedule_id}/context", status_code=status.HTTP_200_OK)
def get_schedule_context(
    schedule_id: str,
    persona_id: str | None = None,
    db: Session = Depends(get_db),
):
    return SyntheticScheduleService(db).get_context(
        schedule_id=schedule_id, persona_id=persona_id
    )


@router.post("/events/{event_record_id}/dispatching", status_code=status.HTTP_200_OK)
def mark_scheduled_event_dispatching(
    event_record_id: str, db: Session = Depends(get_db)
):
    event = SyntheticScheduleService(db).mark_dispatching(event_record_id)
    if not event:
        raise HTTPException(status_code=404, detail="Scheduled event not found.")
    return event


@router.post("/events/{event_record_id}/succeeded", status_code=status.HTTP_200_OK)
def mark_scheduled_event_succeeded(
    event_record_id: str,
    request: SyntheticScheduledEventUpdateRequest,
    db: Session = Depends(get_db),
):
    event = SyntheticScheduleService(db).mark_succeeded(
        event_record_id=event_record_id, result_payload=request.result_payload
    )
    if not event:
        raise HTTPException(status_code=404, detail="Scheduled event not found.")
    return event


@router.post("/events/{event_record_id}/failed", status_code=status.HTTP_200_OK)
def mark_scheduled_event_failed(
    event_record_id: str,
    request: SyntheticScheduledEventUpdateRequest,
    db: Session = Depends(get_db),
):
    event = SyntheticScheduleService(db).mark_failed(
        event_record_id=event_record_id,
        error=request.error or "Scheduled event dispatch failed.",
        result_payload=request.result_payload,
    )
    if not event:
        raise HTTPException(status_code=404, detail="Scheduled event not found.")
    return event


@router.post("/schedules/{schedule_id}/cancel", status_code=status.HTTP_200_OK)
def cancel_future_scheduled_events(schedule_id: str, db: Session = Depends(get_db)):
    return SyntheticScheduleService(db).cancel_future_events(schedule_id=schedule_id)
