import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)

from utils.database import Base
from utils.database import UniversalUUID as UUID, generate_uuid


class FraudAlert(Base):
    """Persisted fraud workflow record tied to suspicious card activity."""

    __tablename__ = "fraud_alerts"
    __table_args__ = (
        Index("idx_fraud_alerts_customer_status", "customer_id", "status"),
        Index("idx_fraud_alerts_thread_id", "message_thread_id"),
        {"schema": "operations"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    customer_id = Column(UUID(as_uuid=True), nullable=False)
    auth_provider_uid = Column(String(128), nullable=False, index=True)
    credit_account_id = Column(UUID(as_uuid=True), nullable=False)
    card_id = Column(UUID(as_uuid=True), nullable=False)
    card_last_four = Column(String(4), nullable=False)
    status = Column(String(32), nullable=False, default="OPEN")
    source = Column(String(64), nullable=False, default="SIMULATION_TARGETED_FRAUD")
    message_thread_id = Column(String(128), nullable=False, unique=True)
    suspicious_authorization_ids = Column(JSON, nullable=False, default=list)
    suspicious_transactions = Column(JSON, nullable=False, default=list)
    remediation_status = Column(String(32), nullable=False, default="NOT_STARTED")
    triaged_at = Column(DateTime, nullable=True)
    triage_summary = Column(String(512), nullable=True)
    selected_disputed_authorization_ids = Column(JSON, nullable=False, default=list)
    selected_disputed_transaction_ids = Column(JSON, nullable=False, default=list)
    provisional_credit_cents = Column(BigInteger, nullable=False, default=0)
    replacement_card_id = Column(UUID(as_uuid=True), nullable=True)
    triage_message_thread_id = Column(String(128), nullable=True)
    triage_message_id = Column(String(128), nullable=True)
    created_at = Column(
        DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    resolved_at = Column(DateTime, nullable=True)


class FraudCaseAction(Base):
    """Durable action history for fraud remediation workflow steps."""

    __tablename__ = "fraud_case_actions"
    __table_args__ = (
        Index("idx_fraud_case_actions_alert", "fraud_alert_id"),
        Index("idx_fraud_case_actions_status", "status"),
        Index("idx_fraud_case_actions_type", "action_type"),
        UniqueConstraint(
            "fraud_alert_id",
            "idempotency_key",
            name="uq_fraud_case_actions_idempotency",
        ),
        {"schema": "operations"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    fraud_alert_id = Column(UUID(as_uuid=True), nullable=False)
    action_type = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="PENDING")
    idempotency_key = Column(String(128), nullable=True)
    request_payload = Column(JSON, nullable=False, default=dict)
    result_payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(
        DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    completed_at = Column(DateTime, nullable=True)


class FraudModelDecision(Base):
    """Explainable fraud model decision snapshot for one card authorization."""

    __tablename__ = "fraud_model_decisions"
    __table_args__ = (
        Index(
            "idx_fraud_model_decisions_customer_created", "customer_id", "created_at"
        ),
        Index(
            "idx_fraud_model_decisions_account_created",
            "credit_account_id",
            "created_at",
        ),
        Index("idx_fraud_model_decisions_card_created", "card_id", "created_at"),
        UniqueConstraint(
            "authorization_id", name="uq_fraud_model_decisions_authorization"
        ),
        {"schema": "operations"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    authorization_id = Column(UUID(as_uuid=True), nullable=False)
    customer_id = Column(UUID(as_uuid=True), nullable=False)
    credit_account_id = Column(UUID(as_uuid=True), nullable=False)
    card_id = Column(UUID(as_uuid=True), nullable=False)
    score = Column(Integer, nullable=False)
    threshold = Column(Integer, nullable=False)
    decision = Column(String(32), nullable=False)
    reason_codes = Column(JSON, nullable=False, default=list)
    feature_snapshot = Column(JSON, nullable=False, default=dict)
    merchant_name = Column(String(255), nullable=True)
    merchant_category_code = Column(String(4), nullable=True)
    transaction_channel = Column(String(32), nullable=True)
    merchant_country_code = Column(String(3), nullable=True)
    merchant_city = Column(String(100), nullable=True)
    merchant_region = Column(String(100), nullable=True)
    model_version = Column(String(64), nullable=False)
    created_at = Column(
        DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )


class ScenarioOutcome(Base):
    """Synthetic scenario feedback label persisted for CDC/lakehouse validation."""

    __tablename__ = "scenario_outcomes"
    __table_args__ = (
        Index(
            "idx_scenario_outcomes_scenario_execution", "scenario_id", "execution_id"
        ),
        Index("idx_scenario_outcomes_authorization", "authorization_id"),
        Index("idx_scenario_outcomes_fraud_alert", "fraud_alert_id"),
        Index("idx_scenario_outcomes_customer_created", "customer_id", "created_at"),
        UniqueConstraint(
            "scenario_id", "execution_id", "event_id", name="uq_scenario_outcomes_event"
        ),
        {"schema": "operations"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    scenario_id = Column(String(128), nullable=False)
    execution_id = Column(String(128), nullable=False)
    event_id = Column(String(128), nullable=False)
    authorization_id = Column(UUID(as_uuid=True), nullable=True)
    transaction_id = Column(UUID(as_uuid=True), nullable=True)
    fraud_alert_id = Column(UUID(as_uuid=True), nullable=True)
    customer_id = Column(UUID(as_uuid=True), nullable=True)
    credit_account_id = Column(UUID(as_uuid=True), nullable=True)
    card_id = Column(UUID(as_uuid=True), nullable=True)
    card_token = Column(String(128), nullable=True)
    outcome_label = Column(String(64), nullable=False)
    expected_reason_codes = Column(JSON, nullable=False, default=list)
    actual_reason_codes = Column(JSON, nullable=False, default=list)
    expected_score_band = Column(String(64), nullable=True)
    actual_risk_score = Column(Integer, nullable=True)
    model_version = Column(String(64), nullable=True)
    synthetic_label = Column(Boolean, nullable=False, default=True)
    operational_action = Column(String(64), nullable=True)
    operational_status = Column(String(64), nullable=True)
    created_at = Column(
        DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )


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

    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
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
