import uuid
from sqlalchemy import Column, String, DateTime, JSON
from utils.database import UniversalUUID as UUID, generate_uuid
from datetime import datetime, timezone
from utils.database import Base

class Escalation(Base):
    __tablename__ = "support_escalations"
    __table_args__ = {'schema': 'operations'}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    room_name = Column(String, nullable=False)
    customer_id = Column(String, nullable=False)
    reason = Column(String, nullable=True)
    status = Column(String, default="PENDING")  # PENDING, ACCEPTED, COMPLETED, ABANDONED
    transcript = Column(JSON, nullable=True)     # Store conversation history
    assigned_to = Column(String, nullable=True)  # Email of the agent who accepted it
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
