from __future__ import annotations

import datetime
from typing import Any

from .database import SessionLocal
from .schemas import ScheduledEventRecord
from .service import SyntheticScheduleService


def _coerce_datetime(value: Any) -> Any:
    if isinstance(value, str):
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


class SyntheticScheduleClient:
    """Data Generator-owned durable schedule access.

    The scheduler is a Data Generator control surface. It stores records in the
    shared operational database, but it does not route schedule lifecycle calls
    through Banking Service.
    """

    def __init__(self, *, session_factory=SessionLocal):
        self.session_factory = session_factory

    def _service(self):
        db = self.session_factory()
        return db, SyntheticScheduleService(db)

    async def create_event(self, payload: dict[str, Any]) -> ScheduledEventRecord:
        normalized = dict(payload)
        normalized["scheduled_for"] = _coerce_datetime(normalized.get("scheduled_for"))
        db, service = self._service()
        try:
            return service.create_event(**normalized)
        finally:
            db.close()

    async def list_events(
        self,
        *,
        schedule_id: str | None = None,
        status_filter: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        db, service = self._service()
        try:
            return service.list_events(
                schedule_id=schedule_id,
                status=status_filter,
                limit=max(1, min(limit, 500)),
            )
        finally:
            db.close()

    async def get_event(self, event_record_id: str) -> ScheduledEventRecord:
        db, service = self._service()
        try:
            event = service.get_event(event_record_id)
            if not event:
                raise KeyError(f"Scheduled event not found: {event_record_id}")
            return event
        finally:
            db.close()

    async def get_context(
        self, *, schedule_id: str, persona_id: str | None = None
    ) -> dict[str, Any]:
        db, service = self._service()
        try:
            return service.get_context(schedule_id=schedule_id, persona_id=persona_id)
        finally:
            db.close()

    async def mark_dispatching(self, event_record_id: str) -> ScheduledEventRecord:
        db, service = self._service()
        try:
            event = service.mark_dispatching(event_record_id)
            if not event:
                raise KeyError(f"Scheduled event not found: {event_record_id}")
            return event
        finally:
            db.close()

    async def mark_succeeded(
        self, event_record_id: str, result_payload: dict[str, Any]
    ) -> ScheduledEventRecord:
        db, service = self._service()
        try:
            event = service.mark_succeeded(
                event_record_id=event_record_id, result_payload=result_payload
            )
            if not event:
                raise KeyError(f"Scheduled event not found: {event_record_id}")
            return event
        finally:
            db.close()

    async def mark_failed(
        self,
        event_record_id: str,
        *,
        error: str,
        result_payload: dict[str, Any] | None = None,
    ) -> ScheduledEventRecord:
        db, service = self._service()
        try:
            event = service.mark_failed(
                event_record_id=event_record_id,
                error=error,
                result_payload=result_payload or {},
            )
            if not event:
                raise KeyError(f"Scheduled event not found: {event_record_id}")
            return event
        finally:
            db.close()

    async def cancel_schedule(self, schedule_id: str) -> dict[str, Any]:
        db, service = self._service()
        try:
            return service.cancel_future_events(schedule_id=schedule_id)
        finally:
            db.close()
