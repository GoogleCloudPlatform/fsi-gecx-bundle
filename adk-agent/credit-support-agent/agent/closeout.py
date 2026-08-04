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

"""Transport-attested voice-session closeout boundaries."""

from __future__ import annotations

import time


def mark_action_completed_for_closeout(
    *,
    originating_customer_event_id: str,
    now_epoch_s: float | None = None,
) -> dict:
    """Record the customer turn that authorized the last completed action."""
    return {
        "status": "ACTION_COMPLETED",
        "originating_customer_event_id": originating_customer_event_id,
        "completed_at_epoch_s": time.time() if now_epoch_s is None else now_epoch_s,
    }


def closeout_block_reason(
    *,
    closeout_boundary: dict | None,
    workflow_authorization: dict | None,
    latest_customer_turn: dict | None,
) -> str | None:
    """Validate action state and turn provenance without interpreting words."""
    authorization = workflow_authorization or {}
    authorization_status = authorization.get("status")
    proposal_checkpoint = authorization.get("evidence_state")
    if proposal_checkpoint in {
        "AWAITING_PRESENTATION",
        "AWAITING_DECISION",
        "DECISION_ATTESTED",
        "COMMIT_IN_FLIGHT",
        "COMMIT_RETRY",
    }:
        return f"PENDING_PROPOSAL_{proposal_checkpoint}"
    if authorization_status in {
        "PREPARED",
        "PENDING",
        "CONFIRMED",
        "EXECUTING",
        "RECOVERY_REQUIRED",
    }:
        return f"WORKFLOW_AUTHORIZATION_{authorization_status}"

    latest = latest_customer_turn or {}
    latest_event_id = str(latest.get("event_id") or "")
    if not latest_event_id:
        return "CLOSEOUT_CUSTOMER_TURN_REQUIRED"

    boundary = closeout_boundary or {}
    if boundary.get("status") != "ACTION_COMPLETED":
        return None
    if latest_event_id == str(boundary.get("originating_customer_event_id") or ""):
        return "LATER_CLOSEOUT_CUSTOMER_TURN_REQUIRED"
    if float(latest.get("observed_at_epoch_s") or 0) <= float(
        boundary.get("completed_at_epoch_s") or 0
    ):
        return "LATER_CLOSEOUT_CUSTOMER_TURN_REQUIRED"
    return None
