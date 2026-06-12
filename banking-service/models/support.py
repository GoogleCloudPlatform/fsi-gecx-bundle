import uuid
from sqlalchemy import Column, String, DateTime, JSON
from datetime import datetime, timezone
from utils.database import Base

class Escalation(Base):
    __tablename__ = "support_escalations"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    room_name = Column(String, nullable=False)
    customer_id = Column(String, nullable=False)
    reason = Column(String, nullable=True)
    status = Column(String, default="PENDING")  # PENDING, ACCEPTED, COMPLETED, ABANDONED
    transcript = Column(JSON, nullable=True)     # Store conversation history
    assigned_to = Column(String, nullable=True)  # Email of the agent who accepted it
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
