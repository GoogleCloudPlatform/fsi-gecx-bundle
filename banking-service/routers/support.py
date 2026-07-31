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

import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from utils.database import get_db
from utils.auth import get_current_user
from models.authentication import ValidatedToken
from services.support import SupportService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/support", tags=["Support Escalations"], dependencies=[Depends(get_current_user)])


def get_support_service(db: Session = Depends(get_db)) -> SupportService:
    return SupportService(db)


class EscalationPayload(BaseModel):
    room_name: str
    customer_id: str
    reason: str
    transcript: list = Field(default_factory=list)
    escalation_id: str | None = None


@router.get("/escalations")
def list_pending_escalations(
    service: SupportService = Depends(get_support_service)
):
    return service.list_pending_escalations()


@router.post("/token")
def get_human_agent_token(
    room_name: str,
    service: SupportService = Depends(get_support_service),
    user_data: ValidatedToken = Depends(get_current_user)
):
    return service.get_human_agent_token(room_name, user_data)


@router.post("/escalations/{escalation_id}/complete")
def complete_escalation(
    escalation_id: str,
    service: SupportService = Depends(get_support_service)
):
    return service.complete_escalation(escalation_id)


@router.post("/escalate")
def escalate_session(
    payload: EscalationPayload,
    service: SupportService = Depends(get_support_service)
):
    return service.escalate_session(payload)


@router.post("/escalations/{escalation_id}/abandon")
def abandon_escalation(
    escalation_id: str,
    service: SupportService = Depends(get_support_service)
):
    return service.abandon_escalation(escalation_id)
