import os
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from livekit import api as lk_api

from utils.database import get_db
from utils.auth import get_current_user
from models.authentication import ValidatedToken
from models.support import Escalation
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/support", tags=["Support Escalations"], dependencies=[Depends(get_current_user)])

LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "secret")

@router.get("/escalations")
def list_pending_escalations(
    db: Session = Depends(get_db)
):
    """Retrieves all pending support escalations that require human presenter takeover."""
    logger.info("Retrieving pending escalations queue...")
    escalations = db.query(Escalation).filter_by(status="PENDING").order_by(Escalation.created_at.desc()).all()
    
    return [
        {
            "id": esc.id,
            "room_name": esc.room_name,
            "customer_id": esc.customer_id,
            "reason": esc.reason,
            "status": esc.status,
            "transcript": esc.transcript,
            "created_at": esc.created_at.isoformat() if esc.created_at else None
        } for esc in escalations
    ]

@router.post("/token")
def get_human_agent_token(
    room_name: str,
    db: Session = Depends(get_db),
    user_data: ValidatedToken = Depends(get_current_user)
):
    """
    Validates employee access and generates a secure LiveKit room token 
    enabling the human agent to take over the specified voice room.
    
    Updates the escalation request state to 'ACCEPTED'.
    """
    agent_email = None
    if user_data and user_data.email:
        agent_email = user_data.email
    elif os.getenv("ALLOW_DEV_AUTH_BYPASS") == "true" or os.getenv("ENV") == "development":
        agent_email = "agent@novahorizon.com"

    if not agent_email:
        logger.error("Security Alert: Unauthorized access attempt without valid email context.")
        raise HTTPException(status_code=401, detail="Unauthorized: Identity email context missing.")

    logger.info(f"Generating LiveKit human token for agent {agent_email} on room {room_name}")
    
    # 1. Verification of the escalation row in DB
    escalation = db.query(Escalation).filter_by(room_name=room_name, status="PENDING").first()
    if not escalation:
        logger.warning(f"No pending escalation found for room {room_name}")
        raise HTTPException(status_code=404, detail="No active or pending escalation found for this room.")
        
    try:
        # 2. Update state to ACCEPTED
        escalation.status = "ACCEPTED"
        escalation.assigned_to = agent_email
        db.commit()
        
        # 3. Generate LiveKit token with specific grants
        token = lk_api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        token.with_identity(f"agent-human-{agent_email}")
        token.with_grants(lk_api.VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True
        ))
        
        return {
            "token": token.to_jwt(),
            "room_name": room_name,
            "escalation_id": escalation.id
        }
    except Exception as e:
        logger.error(f"Failed to generate LiveKit token for agent: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="LiveKit token creation error.")

@router.post("/escalations/{escalation_id}/complete")
def complete_escalation(
    escalation_id: str,
    db: Session = Depends(get_db)
):
    """Marks an active/accepted support escalation as successfully COMPLETED."""
    logger.info(f"Completing escalation session: {escalation_id}")
    escalation = db.query(Escalation).filter_by(id=escalation_id).first()
    if not escalation:
        raise HTTPException(status_code=404, detail="Escalation not found.")
    
    try:
        escalation.status = "COMPLETED"
        db.commit()
        logger.info(f"Escalation {escalation_id} successfully marked as COMPLETED.")
        return {"status": "SUCCESS", "escalation_id": escalation_id}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to complete escalation: {e}")
        raise HTTPException(status_code=500, detail="Database write error.")


class EscalationPayload(BaseModel):
    room_name: str
    customer_id: str
    reason: str
    transcript: list = Field(default_factory=list)
    escalation_id: int | None = None


@router.post("/escalate")
def escalate_session(
    payload: EscalationPayload,
    db: Session = Depends(get_db)
):
    """Creates a new support escalation or updates the transcript of an existing one."""
    logger.info(f"Escalation request: {payload}")
    try:
        if payload.escalation_id is not None:
            existing = db.query(Escalation).filter_by(id=payload.escalation_id).first()
            if existing:
                existing.transcript = payload.transcript
                db.commit()
                logger.info(f"Updated transcript on existing escalation: {payload.escalation_id}")
                return {"status": "SUCCESS", "escalation_id": existing.id}
            else:
                raise HTTPException(status_code=404, detail="Escalation ID not found to update.")
        else:
            escalation = Escalation(
                room_name=payload.room_name,
                customer_id=payload.customer_id,
                reason=payload.reason,
                status="PENDING",
                transcript=payload.transcript
            )
            db.add(escalation)
            db.commit()
            logger.info(f"Created new support escalation: {escalation.id}")
            return {"status": "SUCCESS", "escalation_id": escalation.id}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        db.rollback()
        logger.error(f"Failed to handle escalation request: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/escalations/{escalation_id}/abandon")
def abandon_escalation(
    escalation_id: int,
    db: Session = Depends(get_db)
):
    """Marks an active/pending support escalation as ABANDONED (e.g. user disconnected)."""
    logger.info(f"Abandoning escalation: {escalation_id}")
    escalation = db.query(Escalation).filter_by(id=escalation_id).first()
    if not escalation:
        raise HTTPException(status_code=404, detail="Escalation not found.")
    
    try:
        escalation.status = "ABANDONED"
        db.commit()
        logger.info(f"Escalation {escalation_id} marked as ABANDONED.")
        return {"status": "SUCCESS", "escalation_id": escalation_id}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to abandon escalation: {e}")
        raise HTTPException(status_code=500, detail="Database write error.")
