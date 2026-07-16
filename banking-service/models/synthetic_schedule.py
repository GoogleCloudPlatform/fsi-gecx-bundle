"""Authoritative schema contract for Data Generator scheduled events.

Data Generator keeps its own runtime ORM mapping, but Banking Service owns the
Alembic schema. A contract test prevents the two mappings from drifting.
"""

from sqlalchemy import Column, DateTime, Index, Integer, JSON, String, UniqueConstraint

from utils.database import Base, UniversalUUID as UUID


class SyntheticScheduledEventSchema(Base):
    __tablename__ = "synthetic_scheduled_events"
    __table_args__ = (
        Index("idx_synthetic_scheduled_events_schedule", "schedule_id", "scheduled_for"),
        Index("idx_synthetic_scheduled_events_status_time", "status", "scheduled_for"),
        Index("idx_synthetic_scheduled_events_scenario", "scenario_id", "execution_id"),
        UniqueConstraint(
            "idempotency_key", name="uq_synthetic_scheduled_events_idempotency"
        ),
        {"schema": "operations"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True)
    schedule_id = Column(String(128), nullable=False)
    scenario_id = Column(String(128), nullable=True)
    execution_id = Column(String(128), nullable=True)
    event_id = Column(String(128), nullable=False)
    parent_event_id = Column(String(128), nullable=True)
    event_type = Column(String(64), nullable=False)
    persona_id = Column(String(128), nullable=True)
    status = Column(String(32), nullable=False)
    idempotency_key = Column(String(200), nullable=False)
    scheduled_for = Column(DateTime, nullable=False)
    payload = Column(JSON, nullable=False)
    result_payload = Column(JSON, nullable=False)
    attempts = Column(Integer, nullable=False)
    last_error = Column(String(1024), nullable=True)
    dispatched_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    canceled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)
