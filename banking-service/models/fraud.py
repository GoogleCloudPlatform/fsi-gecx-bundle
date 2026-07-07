import datetime

from sqlalchemy import Column, DateTime, Index, JSON, String

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
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    resolved_at = Column(DateTime, nullable=True)
