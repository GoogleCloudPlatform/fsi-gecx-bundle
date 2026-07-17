"""Banking-owned reset epoch state in the otherwise ADK-owned session schema."""

from sqlalchemy import BigInteger, Column, DateTime, String, text

from utils.database import Base


class VoiceSessionResetEpoch(Base):
    __tablename__ = "reset_epochs"
    __table_args__ = {"schema": "voice_support_sessions"}

    scope_type = Column(String(16), primary_key=True)
    scope_id = Column(String(255), primary_key=True)
    epoch = Column(BigInteger, nullable=False, server_default=text("0"))
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
