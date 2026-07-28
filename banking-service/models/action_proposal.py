"""Durable, runtime-neutral authorization state for consequential actions."""

import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Index,
    JSON,
    String,
    UniqueConstraint,
)

from utils.database import Base
from utils.database import UniversalUUID as UUID, generate_uuid


PROPOSAL_STATUSES = (
    "PROPOSED",
    "PRESENTED",
    "CONFIRMED",
    "COMMITTING",
    "COMMITTED",
    "DECLINED",
    "INVALIDATED",
    "EXPIRED",
)

CONFIRMATION_POLICIES = (
    "NONE",
    "EXPLICIT_VERBAL",
    "EXPLICIT_UI",
    "STEP_UP",
    "HUMAN_APPROVAL",
)


class ActionProposal(Base):
    """Banking-owned proposal envelope; runtimes commit only its opaque id.

    The action payload and its scope are immutable after creation by service
    contract. Lifecycle methods update only status, evidence, outcome, and
    timestamps.
    """

    __tablename__ = "action_proposals"
    __table_args__ = (
        CheckConstraint(
            "status IN ("
            + ", ".join(f"'{value}'" for value in PROPOSAL_STATUSES)
            + ")",
            name="ck_action_proposals_status",
        ),
        CheckConstraint(
            "confirmation_policy IN ("
            + ", ".join(f"'{value}'" for value in CONFIRMATION_POLICIES)
            + ")",
            name="ck_action_proposals_confirmation_policy",
        ),
        UniqueConstraint(
            "customer_id",
            "support_session_id",
            "action_type",
            "idempotency_key",
            name="uq_action_proposals_scope_idempotency",
        ),
        Index(
            "idx_action_proposals_customer_status",
            "customer_id",
            "status",
        ),
        Index(
            "idx_action_proposals_session_status",
            "support_session_id",
            "status",
        ),
        Index("idx_action_proposals_expires_at", "expires_at"),
        {"schema": "operations"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    contract_version = Column(String(32), nullable=False)
    action_type = Column(String(64), nullable=False)
    status = Column(String(24), nullable=False, default="PROPOSED")

    customer_id = Column(UUID(as_uuid=True), nullable=False)
    account_id = Column(UUID(as_uuid=True), nullable=True)
    support_session_id = Column(String(255), nullable=False)
    runtime_name = Column(String(64), nullable=False)
    runtime_session_id = Column(String(255), nullable=False)
    originating_customer_turn_id = Column(String(255), nullable=False)
    reset_generation = Column(String(64), nullable=False)

    confirmation_policy = Column(String(32), nullable=False)
    action_payload = Column(JSON, nullable=False)
    payload_fingerprint = Column(String(64), nullable=False)
    customer_safe_summary = Column(String(2000), nullable=False)
    catalog_snapshot_id = Column(String(255), nullable=True)
    idempotency_key = Column(String(128), nullable=False)

    presented_assistant_turn_id = Column(String(255), nullable=True)
    confirmation_customer_turn_id = Column(String(255), nullable=True)
    confirmation_evidence = Column(JSON, nullable=True)
    result_payload = Column(JSON, nullable=True)
    invalidation_reason = Column(String(255), nullable=True)

    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        onupdate=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    presented_at = Column(DateTime(timezone=True), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    commit_started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
