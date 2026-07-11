from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy.orm import Session

from models.fraud import SyntheticScheduledEvent
from repositories.synthetic_schedule import SyntheticScheduledEventRepository


def _dt(value: datetime.datetime) -> datetime.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


class SyntheticScheduleService:
    def __init__(self, db: Session):
        self.repo = SyntheticScheduledEventRepository(db)
        self.db = db

    @staticmethod
    def serialize_event(event: SyntheticScheduledEvent) -> dict[str, Any]:
        return {
            "id": str(event.id),
            "schedule_id": event.schedule_id,
            "scenario_id": event.scenario_id,
            "execution_id": event.execution_id,
            "event_id": event.event_id,
            "parent_event_id": event.parent_event_id,
            "event_type": event.event_type,
            "persona_id": event.persona_id,
            "status": event.status,
            "idempotency_key": event.idempotency_key,
            "scheduled_for": _dt(event.scheduled_for).isoformat()
            if event.scheduled_for
            else None,
            "payload": event.payload or {},
            "result_payload": event.result_payload or {},
            "attempts": event.attempts or 0,
            "last_error": event.last_error,
            "dispatched_at": _dt(event.dispatched_at).isoformat()
            if event.dispatched_at
            else None,
            "completed_at": _dt(event.completed_at).isoformat()
            if event.completed_at
            else None,
            "canceled_at": _dt(event.canceled_at).isoformat()
            if event.canceled_at
            else None,
            "created_at": _dt(event.created_at).isoformat()
            if event.created_at
            else None,
            "updated_at": _dt(event.updated_at).isoformat()
            if event.updated_at
            else None,
        }

    def create_event(self, **kwargs) -> dict[str, Any]:
        event = self.repo.create_event(**kwargs)
        self.db.commit()
        self.db.refresh(event)
        return self.serialize_event(event)

    def list_events(
        self,
        *,
        schedule_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        events = self.repo.list_events(
            schedule_id=schedule_id, status=status, limit=limit
        )
        return {"count": len(events), "events": [self.serialize_event(e) for e in events]}

    def get_event(self, event_record_id: str) -> dict[str, Any] | None:
        event = self.repo.get_by_id(event_record_id)
        return self.serialize_event(event) if event else None

    def get_context(
        self,
        *,
        schedule_id: str,
        persona_id: str | None = None,
    ) -> dict[str, Any]:
        events = self.repo.list_completed_before(
            schedule_id=schedule_id, persona_id=persona_id
        )
        return {"events": [self.serialize_event(e) for e in events]}

    def mark_dispatching(self, event_record_id: str) -> dict[str, Any] | None:
        event = self.repo.mark_dispatching(event_record_id)
        self.db.commit()
        return self.serialize_event(event) if event else None

    def mark_succeeded(
        self, *, event_record_id: str, result_payload: dict | None = None
    ) -> dict[str, Any] | None:
        event = self.repo.mark_succeeded(
            event_record_id=event_record_id, result_payload=result_payload
        )
        self.db.commit()
        return self.serialize_event(event) if event else None

    def mark_failed(
        self,
        *,
        event_record_id: str,
        error: str,
        result_payload: dict | None = None,
    ) -> dict[str, Any] | None:
        event = self.repo.mark_failed(
            event_record_id=event_record_id,
            error=error,
            result_payload=result_payload,
        )
        self.db.commit()
        return self.serialize_event(event) if event else None

    def cancel_future_events(self, *, schedule_id: str) -> dict[str, Any]:
        canceled = self.repo.cancel_future_events(schedule_id=schedule_id)
        self.db.commit()
        return {"schedule_id": schedule_id, "canceled_events": canceled}
