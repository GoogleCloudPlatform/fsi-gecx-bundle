from __future__ import annotations

import datetime
import logging
import os
import uuid as _uuid
from collections.abc import Generator

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.types import TypeDecorator, Uuid

logger = logging.getLogger(__name__)


class StringComparableUUID(_uuid.UUID):
    def __eq__(self, other):
        if isinstance(other, str):
            try:
                return super().__eq__(_uuid.UUID(other))
            except ValueError:
                return str(self) == other
        return super().__eq__(other)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return super().__hash__()


def generate_uuid():
    return StringComparableUUID(str(_uuid.uuid4()))


class UniversalUUID(TypeDecorator):
    impl = Uuid
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return _uuid.UUID(value)
            except ValueError:
                return value
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, _uuid.UUID):
            return StringComparableUUID(str(value))
        if isinstance(value, str):
            try:
                return StringComparableUUID(value)
            except ValueError:
                return value
        return value


Base = declarative_base()


class SyntheticScheduledEvent(Base):
    """Durable synthetic data-generator event queued for timed execution."""

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

    id = Column(UniversalUUID(as_uuid=True), primary_key=True, default=generate_uuid)
    schedule_id = Column(String(128), nullable=False)
    scenario_id = Column(String(128), nullable=True)
    execution_id = Column(String(128), nullable=True)
    event_id = Column(String(128), nullable=False)
    parent_event_id = Column(String(128), nullable=True)
    event_type = Column(String(64), nullable=False)
    persona_id = Column(String(128), nullable=True)
    status = Column(String(32), nullable=False, default="SCHEDULED")
    idempotency_key = Column(String(200), nullable=False)
    scheduled_for = Column(DateTime, nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    result_payload = Column(JSON, nullable=False, default=dict)
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(String(1024), nullable=True)
    dispatched_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    canceled_at = Column(DateTime, nullable=True)
    created_at = Column(
        DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        onupdate=lambda: datetime.datetime.now(datetime.timezone.utc),
    )


DATABASE_URL = os.getenv("DATA_GENERATOR_DATABASE_URL") or os.getenv("DATABASE_URL")


def get_iam_connection(url_str: str):
    import google.auth
    import google.auth.transport.requests
    import psycopg2

    url = make_url(url_str)
    credentials, _project = google.auth.default(
        scopes=[
            "https://www.googleapis.com/auth/sqlservice.login",
            "https://www.googleapis.com/auth/cloud-platform",
        ]
    )
    credentials.refresh(google.auth.transport.requests.Request())

    host_val = url.host or url.query.get("host")
    conn_params = {
        "host": host_val,
        "database": url.database,
        "user": url.username,
        "password": credentials.token,
    }
    if host_val and not host_val.startswith("/"):
        conn_params["port"] = url.port or 5432
        conn_params["sslmode"] = url.query.get("sslmode", "verify-full")
    return psycopg2.connect(**conn_params)


def create_scheduler_engine(url_str: str | None = None, **kwargs):
    db_url = url_str or DATABASE_URL or "sqlite:///.sqlite/data-generator-scheduler.db"
    engine_args = kwargs.copy()
    connect_args = {}

    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        exec_opts = engine_args.get("execution_options", {}).copy()
        exec_opts["schema_translate_map"] = {"operations": None}
        engine_args["execution_options"] = exec_opts
        if db_url != "sqlite:///:memory:":
            path_part = db_url.split("sqlite://", 1)[1].lstrip("/")
            db_dir = os.path.dirname(path_part)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
    elif db_url.startswith("postgresql"):
        engine_args.setdefault("pool_size", int(os.getenv("DB_POOL_SIZE", "5")))
        engine_args.setdefault("max_overflow", int(os.getenv("DB_MAX_OVERFLOW", "10")))
        engine_args.setdefault("pool_timeout", int(os.getenv("DB_POOL_TIMEOUT", "30")))
        engine_args.setdefault("pool_recycle", int(os.getenv("DB_POOL_RECYCLE", "900")))
        engine_args.setdefault("pool_pre_ping", True)
        if os.getenv("DB_IAM_AUTH", "false").lower() == "true":
            logger.info("Using GCP IAM authentication for Data Generator scheduler DB.")
            engine_args["creator"] = lambda: get_iam_connection(db_url)

    sanitized_url = make_url(db_url).render_as_string(hide_password=True)
    logger.info("Creating Data Generator scheduler database engine for %s", sanitized_url)
    return create_engine(db_url, connect_args=connect_args, **engine_args)


engine = create_scheduler_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def ensure_scheduler_tables() -> None:
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
