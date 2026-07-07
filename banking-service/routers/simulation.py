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

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from models.authentication import ValidatedToken
from services.simulation import SimulationService
from utils.auth import get_current_user
from utils.database import get_db

logger = logging.getLogger(__name__)

def verify_presenter_domain(token: ValidatedToken = Depends(get_current_user)) -> ValidatedToken:
    """Security dependency restricting simulation suite operations to authorized presenter domains."""
    email = token.email
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authenticated email not found in token claims."
        )
    email_lower = email.lower()
    allowed_domains = ["google.com", "gcp.solutions", "altostrat.com"]
    if not any(email_lower.endswith(f"@{domain}") for domain in allowed_domains):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Simulation actions are restricted to authorized presenter domains."
        )
    return token

router = APIRouter(prefix="/api/v1/simulation", tags=["simulation"], dependencies=[Depends(verify_presenter_domain)])
v1_router = APIRouter(prefix="/v1/simulation", tags=["simulation"], dependencies=[Depends(verify_presenter_domain)])
alias_router = APIRouter(prefix="/simulation", tags=["simulation"], dependencies=[Depends(verify_presenter_domain)])

@router.post("/provision-my-demo", status_code=status.HTTP_201_CREATED)
@v1_router.post("/provision-my-demo", status_code=status.HTTP_201_CREATED)
@alias_router.post("/provision-my-demo", status_code=status.HTTP_201_CREATED)
def provision_my_demo(
    token: ValidatedToken = Depends(verify_presenter_domain),
    db: Session = Depends(get_db)
):
    """
    Provisions a complete, isolated banking suite with realistic history for the logged-in user.
    """
    return SimulationService(db).provision_my_demo(token)

@router.post("/reset-my-demo", status_code=status.HTTP_200_OK)
@v1_router.post("/reset-my-demo", status_code=status.HTTP_200_OK)
@alias_router.post("/reset-my-demo", status_code=status.HTTP_200_OK)
def reset_my_demo(
    token: ValidatedToken = Depends(verify_presenter_domain),
    db: Session = Depends(get_db)
):
    """
    Clears credit card transactions, resets credit card balances to $0, and resets checking/savings deposit accounts.
    """
    return SimulationService(db).reset_my_demo(token)

@router.post("/surge", status_code=status.HTTP_200_OK)
@v1_router.post("/surge", status_code=status.HTTP_200_OK)
@alias_router.post("/surge", status_code=status.HTTP_200_OK)
async def simulate_activity_surge(
    token: ValidatedToken = Depends(verify_presenter_domain),
    db: Session = Depends(get_db)
):
    """
    Commands the simulation client to immediately fire 50 rapid-fire card swipes over 10 seconds,
    passing the full active card pool to hydrate the CDC transaction pipeline.
    """
    del token
    return await SimulationService(db).dispatch_spend_surge()

@router.post("/inject-anomaly", status_code=status.HTTP_200_OK)
@v1_router.post("/inject-anomaly", status_code=status.HTTP_200_OK)
@alias_router.post("/inject-anomaly", status_code=status.HTTP_200_OK)
def inject_targeted_fraud(
    token: ValidatedToken = Depends(verify_presenter_domain),
    db: Session = Depends(get_db)
):
    """
    Injects a high-velocity card-not-present (CNP) and international retail fraud surge against the CE presenter's card.
    simulating someone who skimmed or found their physical card while traveling in Riviera Maya.
    """
    return SimulationService(db).inject_targeted_fraud(token)

@router.post("/inject-late-fee", status_code=status.HTTP_200_OK)
@v1_router.post("/inject-late-fee", status_code=status.HTTP_200_OK)
@alias_router.post("/inject-late-fee", status_code=status.HTTP_200_OK)
def inject_late_fee(
    token: ValidatedToken = Depends(verify_presenter_domain),
    db: Session = Depends(get_db)
):
    """
    Injects a posted Late Fee transaction ($35.00) against the presenter's active credit card
    to enable standalone late fee reversal scripts or live voice demos.
    """
    return SimulationService(db).inject_late_fee(token)

@router.get("/global-stream", status_code=status.HTTP_200_OK)
@v1_router.get("/global-stream", status_code=status.HTTP_200_OK)
@alias_router.get("/global-stream", status_code=status.HTTP_200_OK)
def get_global_stream(
    token: ValidatedToken = Depends(verify_presenter_domain),
    db: Session = Depends(get_db)
):
    """
    Returns a global real-time stream of recent card authorizations and settlements
    to animate the Admin Simulation Lakehouse CDC replication monitor.
    """
    del token
    return SimulationService(db).get_global_stream()


@router.get("/cdc-status", status_code=status.HTTP_200_OK)
@v1_router.get("/cdc-status", status_code=status.HTTP_200_OK)
@alias_router.get("/cdc-status", status_code=status.HTTP_200_OK)
def get_cdc_status(
    token: ValidatedToken = Depends(verify_presenter_domain),
    db: Session = Depends(get_db)
):
    """
    Compares the latest operational card write to the latest replicated BigQuery lakehouse row.
    """
    del token
    return SimulationService(db).get_cdc_status()




@router.get("/stream-sse")
@v1_router.get("/stream-sse")
@alias_router.get("/stream-sse")
async def stream_sse(
    token: ValidatedToken = Depends(verify_presenter_domain),
    db: Session = Depends(get_db)
):
    """
    Push-based Server-Sent Events (SSE) stream delivering real-time CDC lakehouse transactions
    directly to the Admin Simulation UI without requiring manual refreshes or client-side polling.
    """
    return StreamingResponse(SimulationService(db).stream_payload(token), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no"
    })
