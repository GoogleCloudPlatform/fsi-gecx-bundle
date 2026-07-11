import datetime

from sqlalchemy.orm import Session

from models.fraud import SyntheticScheduledEvent


class SyntheticScheduledEventRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_event(
        self,
        *,
        schedule_id: str,
        event_id: str,
        event_type: str,
        scheduled_for: datetime.datetime,
        idempotency_key: str,
        scenario_id: str | None = None,
        execution_id: str | None = None,
        parent_event_id: str | None = None,
        persona_id: str | None = None,
        payload: dict | None = None,
    ) -> SyntheticScheduledEvent:
        existing = self.get_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        event = SyntheticScheduledEvent(
            schedule_id=schedule_id,
            scenario_id=scenario_id,
            execution_id=execution_id,
            event_id=event_id,
            parent_event_id=parent_event_id,
            event_type=event_type,
            persona_id=persona_id,
            scheduled_for=scheduled_for,
            idempotency_key=idempotency_key,
            payload=payload or {},
        )
        self.db.add(event)
        self.db.flush()
        return event

    def get_by_id(self, event_record_id) -> SyntheticScheduledEvent | None:
        return (
            self.db.query(SyntheticScheduledEvent)
            .filter(SyntheticScheduledEvent.id == event_record_id)
            .first()
        )

    def get_by_idempotency_key(
        self, idempotency_key: str
    ) -> SyntheticScheduledEvent | None:
        return (
            self.db.query(SyntheticScheduledEvent)
            .filter(SyntheticScheduledEvent.idempotency_key == idempotency_key)
            .first()
        )

    def list_events(
        self,
        *,
        schedule_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[SyntheticScheduledEvent]:
        query = self.db.query(SyntheticScheduledEvent)
        if schedule_id:
            query = query.filter(SyntheticScheduledEvent.schedule_id == schedule_id)
        if status:
            query = query.filter(SyntheticScheduledEvent.status == status)
        return (
            query.order_by(SyntheticScheduledEvent.scheduled_for.asc())
            .limit(limit)
            .all()
        )

    def list_completed_before(
        self,
        *,
        schedule_id: str,
        persona_id: str | None = None,
    ) -> list[SyntheticScheduledEvent]:
        query = self.db.query(SyntheticScheduledEvent).filter(
            SyntheticScheduledEvent.schedule_id == schedule_id,
            SyntheticScheduledEvent.status == "SUCCEEDED",
        )
        if persona_id:
            query = query.filter(SyntheticScheduledEvent.persona_id == persona_id)
        return query.order_by(SyntheticScheduledEvent.completed_at.asc()).all()

    def mark_dispatching(self, event_record_id) -> SyntheticScheduledEvent | None:
        event = self.get_by_id(event_record_id)
        if not event:
            return None
        if event.status in {"SUCCEEDED", "CANCELED"}:
            return event
        event.status = "DISPATCHING"
        event.attempts = int(event.attempts or 0) + 1
        event.dispatched_at = datetime.datetime.now(datetime.timezone.utc)
        self.db.add(event)
        self.db.flush()
        return event

    def mark_succeeded(
        self,
        *,
        event_record_id,
        result_payload: dict | None = None,
    ) -> SyntheticScheduledEvent | None:
        event = self.get_by_id(event_record_id)
        if not event:
            return None
        event.status = "SUCCEEDED"
        event.result_payload = result_payload or {}
        event.completed_at = datetime.datetime.now(datetime.timezone.utc)
        event.last_error = None
        self.db.add(event)
        self.db.flush()
        return event

    def mark_failed(
        self,
        *,
        event_record_id,
        error: str,
        result_payload: dict | None = None,
    ) -> SyntheticScheduledEvent | None:
        event = self.get_by_id(event_record_id)
        if not event:
            return None
        event.status = "FAILED"
        event.last_error = error[:1024]
        event.result_payload = result_payload or {}
        self.db.add(event)
        self.db.flush()
        return event

    def cancel_future_events(self, *, schedule_id: str) -> int:
        now = datetime.datetime.now(datetime.timezone.utc)
        events = (
            self.db.query(SyntheticScheduledEvent)
            .filter(
                SyntheticScheduledEvent.schedule_id == schedule_id,
                SyntheticScheduledEvent.status.in_(["SCHEDULED", "FAILED"]),
                SyntheticScheduledEvent.scheduled_for >= now,
            )
            .all()
        )
        for event in events:
            event.status = "CANCELED"
            event.canceled_at = now
            self.db.add(event)
        self.db.flush()
        return len(events)
