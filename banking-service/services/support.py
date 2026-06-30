# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import logging
from typing import List, Dict, Any
from fastapi import HTTPException
from sqlalchemy.orm import Session
from livekit import api as lk_api

from models.authentication import ValidatedToken
from models.support import Escalation
from repositories.support import SupportRepository

logger = logging.getLogger(__name__)

LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "secret")


class SupportService:
    """Service layer encapsulating human support escalations and LiveKit voice takeover."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = SupportRepository(db)

    def list_pending_escalations(self) -> List[Dict[str, Any]]:
        logger.info("Retrieving pending escalations queue...")
        escalations = self.repo.list_pending()
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

    def get_human_agent_token(self, room_name: str, user_data: ValidatedToken) -> Dict[str, Any]:
        agent_email = None
        if user_data and user_data.email:
            agent_email = user_data.email
        elif os.getenv("ALLOW_DEV_AUTH_BYPASS") == "true" or os.getenv("ENV") == "development":
            agent_email = "agent@novahorizon.com"

        if not agent_email:
            logger.error("Security Alert: Unauthorized access attempt without valid email context.")
            raise HTTPException(status_code=401, detail="Unauthorized: Identity email context missing.")

        logger.info(f"Generating LiveKit human token for agent {agent_email} on room {room_name}")

        escalation = self.repo.get_pending_by_room(room_name)
        if not escalation:
            logger.warning(f"No pending escalation found for room {room_name}")
            raise HTTPException(status_code=404, detail="No active or pending escalation found for this room.")

        try:
            escalation.status = "ACCEPTED"
            escalation.assigned_to = agent_email
            self.repo.save(escalation)
            self.db.commit()

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
            self.db.rollback()
            raise HTTPException(status_code=500, detail="LiveKit token creation error.")

    def complete_escalation(self, escalation_id: int) -> Dict[str, Any]:
        logger.info(f"Completing escalation session: {escalation_id}")
        escalation = self.repo.get_by_id(escalation_id)
        if not escalation:
            raise HTTPException(status_code=404, detail="Escalation not found.")

        try:
            escalation.status = "COMPLETED"
            self.repo.save(escalation)
            self.db.commit()
            logger.info(f"Escalation {escalation_id} successfully marked as COMPLETED.")
            return {"status": "SUCCESS", "escalation_id": escalation_id}
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to complete escalation: {e}")
            raise HTTPException(status_code=500, detail="Database write error.")

    def escalate_session(self, payload: Any) -> Dict[str, Any]:
        logger.info(f"Escalation request: {payload}")
        try:
            if payload.escalation_id is not None:
                existing = self.repo.get_by_id(payload.escalation_id)
                if existing:
                    existing.transcript = payload.transcript
                    self.repo.save(existing)
                    self.db.commit()
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
                self.repo.save(escalation)
                self.db.commit()
                logger.info(f"Created new support escalation: {escalation.id}")
                return {"status": "SUCCESS", "escalation_id": escalation.id}
        except Exception as e:
            if isinstance(e, HTTPException):
                raise e
            self.db.rollback()
            logger.error(f"Failed to handle escalation request: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def abandon_escalation(self, escalation_id: int) -> Dict[str, Any]:
        logger.info(f"Abandoning escalation: {escalation_id}")
        escalation = self.repo.get_by_id(escalation_id)
        if not escalation:
            raise HTTPException(status_code=404, detail="Escalation not found.")

        try:
            escalation.status = "ABANDONED"
            self.repo.save(escalation)
            self.db.commit()
            logger.info(f"Escalation {escalation_id} marked as ABANDONED.")
            return {"status": "SUCCESS", "escalation_id": escalation_id}
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to abandon escalation: {e}")
            raise HTTPException(status_code=500, detail="Database write error.")
