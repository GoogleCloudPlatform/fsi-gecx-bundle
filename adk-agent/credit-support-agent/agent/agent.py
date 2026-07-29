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
import contextvars
import time
import google
import httpx
from google.adk.agents import Agent
from google.adk.planners import BuiltInPlanner
from google.genai.types import ThinkingConfig
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams, create_mcp_http_client
from google.adk.tools import ToolContext

from agent.events import DataChannelEvent, INTERNAL_TOOL_RUNTIME_STATUS
from agent.closeout import (
    closeout_block_reason,
    invalidate_closeout_checkpoint,
    open_closeout_checkpoint,
)
from agent.guidance_snapshot import guidance_observability_payload
from agent.log_safety import (
    stable_log_reference,
    tool_args_log_summary,
    tool_response_is_expected_checkpoint,
    tool_response_succeeded,
    tool_result_log_summary,
)
from agent.telemetry import record_action_proposal_event, record_tool_completed
from agent.fraud_voice import (
    build_triage_model_result,
    mark_fraud_tool_completed,
    validate_fraud_tool_sequence,
)
from agent.instructions import INSTRUCTION_TEXT
from agent.reset_guard import validate_reset_generation
from agent.tooling import LEGACY_DIRECT_ACTION_TOOLS, LiveMcpToolset
from agent.workflow_authorization import (
    PROVISION_GOOGLE_WALLET,
    REISSUE_CARD,
    TRIAGE_CUSTOMER_REPORTED_FRAUD,
    TRIAGE_FRAUD_CASE,
    action_payload_fingerprint,
    authorize_from_model_tool_intent,
    create_workflow_authorization,
    invalidate_workflow_authorization,
    mark_authorization_completed,
    mark_authorization_executing,
    mark_authorization_recovery_required,
    validate_workflow_authorization,
)

PROPOSAL_ACTION_BY_TOOL = {
    "propose_fraud_triage": TRIAGE_FRAUD_CASE,
    "propose_card_reissue": REISSUE_CARD,
    "propose_wallet_provisioning": PROVISION_GOOGLE_WALLET,
}
COMMIT_ACTION_BY_TOOL = {
    "commit_fraud_triage": TRIAGE_FRAUD_CASE,
    "commit_card_reissue": REISSUE_CARD,
    "commit_wallet_provisioning": PROVISION_GOOGLE_WALLET,
}
PROPOSAL_DECISION_TOOLS = {
    *COMMIT_ACTION_BY_TOOL,
    "decide_action_proposal",
}
AUTHORIZATION_EXECUTION_TOOLS = {
    *COMMIT_ACTION_BY_TOOL,
    "triage_customer_reported_fraud",
}

LOCATION = os.getenv("LOCATION", "us-central1")
project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
if not project_id:
    _, project_id = google.auth.default()
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project_id)
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", LOCATION)
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")

BANKING_SERVICE_URL = os.getenv("BANKING_SERVICE_URL", "http://localhost:8080").rstrip("/")
active_customer_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("active_customer_id", default="jane.doe@example.com")
session_event_callback_var: contextvars.ContextVar = contextvars.ContextVar("session_event_callback", default=None)
session_should_end_var: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "session_should_end", default=None
)
is_processing_tool_var: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "is_processing_tool", default=None
)
latest_customer_turn_var: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "latest_customer_turn", default=None
)
proposal_runtime_context_var: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "proposal_runtime_context", default=None
)


def get_banking_service_mcp_url() -> str:
    explicit_url = os.getenv("BANKING_SERVICE_MCP_URL")
    if explicit_url:
        return explicit_url.rstrip("/") + "/"

    base_url = BANKING_SERVICE_URL.rstrip("/")
    if base_url.endswith("/api"):
        base_url = base_url[:-4]
    default_root_path = "api" if ".run.app" in base_url else ""
    root_path = os.getenv("BANKING_SERVICE_ROOT_PATH", default_root_path).strip("/")
    mcp_path = f"/{root_path}/mcp/" if root_path else "/mcp/"
    return f"{base_url}{mcp_path}"

def build_log_context(state: dict | None = None, **extra) -> dict:
    context = {
        "customer_ref": stable_log_reference(active_customer_id_var.get(), prefix="customer"),
    }
    if state:
        context.update({
            "room_ref": stable_log_reference(state.get("room_name"), prefix="room"),
            "session_ref": stable_log_reference(
                state.get("session_id"), prefix="session"
            ),
            "mode": state.get("mode"),
        })
        fraud_context = state.get("fraud_context") or {}
        fraud_playbook = state.get("fraud_playbook") or {}
        context.update({
            "fraud_alert_ref": stable_log_reference(
                fraud_context.get("fraud_alert_id") or fraud_playbook.get("fraud_alert_id"),
                prefix="alert",
            ),
            "fraud_entry_mode": fraud_playbook.get("entry_mode"),
            "fraud_alert_inspected": fraud_playbook.get("open_alert_inspected"),
            "fraud_resolution_completed": fraud_playbook.get("resolution_completed"),
            "wallet_authorization_status": fraud_playbook.get("wallet_response_status"),
            "workflow_authorization_action": (
                fraud_playbook.get("workflow_authorization") or {}
            ).get("action"),
            "workflow_authorization_status": (
                fraud_playbook.get("workflow_authorization") or {}
            ).get("status"),
            "escalation_status": fraud_playbook.get("escalation_status"),
            "completion_status": fraud_playbook.get("completion_status"),
        })
    context.update({key: value for key, value in extra.items() if value is not None})
    return context


def format_log_context(state: dict | None = None, **extra) -> str:
    context = build_log_context(state=state, **extra)
    return " ".join(f"{key}={value}" for key, value in context.items())

def register_event_callback(cb):
    session_event_callback_var.set(cb)


def bind_session_context(
    customer_id: str,
    callback,
    *,
    support_session_id: str | None = None,
    runtime_name: str = "ADK_GEMINI_LIVE",
    runtime_session_id: str | None = None,
):
    """Binds per-session customer and callback context and resets transient flags."""
    return {
        "customer": active_customer_id_var.set(customer_id),
        "callback": session_event_callback_var.set(callback),
        # Session tasks inherit ContextVar values, but assignments made inside
        # child tasks do not flow back to their parent. Share mutable holders
        # so the voice loop, transcript listeners, and tool callbacks observe
        # the same session signals.
        "should_end": session_should_end_var.set({"requested": False}),
        "is_processing": is_processing_tool_var.set({"active": False}),
        "latest_customer_turn": latest_customer_turn_var.set({
            "latest": None,
            "pending_ingress_turns": [],
        }),
        "proposal_runtime_context": proposal_runtime_context_var.set({
            "support_session_id": support_session_id or runtime_session_id or "",
            "runtime_name": runtime_name,
            "runtime_session_id": runtime_session_id or support_session_id or "",
            "reset_generation": "",
            "catalog_snapshot_id": None,
            "confirmation": None,
        }),
    }


def reset_session_context(tokens: dict) -> None:
    """Restores prior context-var state for a completed session."""
    if not tokens:
        return
    proposal_runtime_context_var.reset(tokens["proposal_runtime_context"])
    is_processing_tool_var.reset(tokens["is_processing"])
    latest_customer_turn_var.reset(tokens["latest_customer_turn"])
    session_should_end_var.reset(tokens["should_end"])
    session_event_callback_var.reset(tokens["callback"])
    active_customer_id_var.reset(tokens["customer"])


def configure_proposal_runtime_context(
    *, reset_generation: str, catalog_snapshot_id: str | None
) -> None:
    holder = proposal_runtime_context_var.get()
    if holder is None:
        return
    holder["reset_generation"] = str(reset_generation or "")
    holder["catalog_snapshot_id"] = catalog_snapshot_id


def _proposal_transport_headers(*, customer_turn_id: str) -> dict[str, str]:
    holder = proposal_runtime_context_var.get() or {}
    confirmation = holder.get("confirmation") or {}
    protected_confirmation_turn_id = str(
        confirmation.get("confirmation_turn_id") or ""
    )
    headers = {
        "x-support-session-id": str(holder.get("support_session_id") or ""),
        "x-runtime-name": str(holder.get("runtime_name") or ""),
        "x-runtime-session-id": str(holder.get("runtime_session_id") or ""),
        "x-customer-turn-id": protected_confirmation_turn_id
        or str(customer_turn_id or ""),
        "x-reset-generation": str(holder.get("reset_generation") or ""),
    }
    if holder.get("catalog_snapshot_id"):
        headers["x-catalog-snapshot-id"] = str(holder["catalog_snapshot_id"])
    if confirmation:
        headers.update({
            "x-proposal-presentation-turn-id": str(confirmation.get("presentation_turn_id") or ""),
            "x-proposal-confirmation-turn-id": str(confirmation.get("confirmation_turn_id") or ""),
            "x-proposal-confirmation-method": "EXPLICIT_VERBAL",
            "x-proposal-confirmation-source": "MODEL_TOOL_INTENT",
        })
    return headers


def _record_commit_proposal_event(
    *,
    state: dict,
    tool_name: str,
    args: dict,
    result: dict | None,
    outcome: str,
    latency_ms: float,
) -> None:
    runtime_context = proposal_runtime_context_var.get() or {}
    authorization = (state.get("fraud_playbook") or {}).get("workflow_authorization") or {}
    structured = result or {}
    record_action_proposal_event(
        runtime=str(runtime_context.get("runtime_name") or "ADK_GEMINI_LIVE"),
        support_session_id=str(runtime_context.get("support_session_id") or state.get("session_id") or ""),
        proposal_id=str(args.get("proposal_id") or authorization.get("proposal_id") or "") or None,
        contract_version=str(
            authorization.get("contract_version")
            or structured.get("contract_version")
            or "unknown"
        ),
        catalog_snapshot_id=runtime_context.get("catalog_snapshot_id"),
        tool=tool_name,
        outcome=str(structured.get("status") or outcome),
        latency_ms=latency_ms,
        invalidation_reason=structured.get("invalidation_reason") or structured.get("error"),
        banking_outcome=structured.get("outcome"),
    )


def is_session_end_requested() -> bool:
    return bool((session_should_end_var.get() or {}).get("requested"))


def request_session_end() -> None:
    holder = session_should_end_var.get()
    if holder is None:
        session_should_end_var.set({"requested": True})
    else:
        holder["requested"] = True


def clear_session_end_request() -> None:
    holder = session_should_end_var.get()
    if holder is None:
        session_should_end_var.set({"requested": False})
    else:
        holder["requested"] = False


def is_tool_processing() -> bool:
    return bool((is_processing_tool_var.get() or {}).get("active"))


def record_customer_turn(
    transcript: str,
    *,
    event_id: str | None = None,
    observed_at_epoch_s: float | None = None,
    pending_ingress: bool = False,
    consume_pending: bool = False,
) -> dict | None:
    """Register a customer turn and return its canonical runtime evidence."""
    text = str(transcript or "").strip()
    if not text:
        return None
    observed_at = time.time() if observed_at_epoch_s is None else observed_at_epoch_s
    holder = latest_customer_turn_var.get()
    if holder is None:
        holder = {"latest": None, "pending_ingress_turns": []}
        latest_customer_turn_var.set(holder)
    pending_turns = holder.setdefault("pending_ingress_turns", [])
    if consume_pending and pending_turns:
        turn = dict(pending_turns.pop(0))
        turn["pending_ingress"] = False
        if event_id and event_id != turn.get("event_id"):
            turn["runtime_event_id"] = event_id
        holder["latest"] = turn
        return turn
    turn = {
        "event_id": event_id or f"customer-turn-{time.time_ns()}",
        "observed_at_epoch_s": observed_at,
        "pending_ingress": pending_ingress,
    }
    if pending_ingress:
        pending_turns.append(turn)
    holder["latest"] = turn
    return turn


def set_tool_processing(is_processing: bool) -> None:
    holder = is_processing_tool_var.get()
    if holder is None:
        is_processing_tool_var.set({"active": is_processing})
    else:
        holder["active"] = is_processing


def notify_event(event_dict):
    cb = session_event_callback_var.get()
    if cb:
        try:
            cb(event_dict)
        except Exception:
            pass

# Custom dynamic auth class for OIDC token refreshing
class DynamicGoogleAuth(httpx.Auth):
    async def async_auth_flow(self, request: httpx.Request):
        token = get_auth_token_for_audience(BANKING_SERVICE_URL)
        request.headers["Authorization"] = f"Bearer {token}"
        request.headers["x-target-customer-id"] = active_customer_id_var.get()
        latest_turn = (latest_customer_turn_var.get() or {}).get("latest") or {}
        request.headers.update(_proposal_transport_headers(
            customer_turn_id=str(latest_turn.get("event_id") or "unknown-turn")
        ))
        yield request

def get_auth_token_for_audience(audience: str) -> str:
    if os.getenv("ENV") == "development" or os.getenv("ALLOW_DEV_AUTH_BYPASS") == "true":
        return "mock-token"
    
    try:
        import google.auth.transport.requests
        import google.oauth2.id_token
        auth_req = google.auth.transport.requests.Request()
        return google.oauth2.id_token.fetch_id_token(auth_req, audience)
    except Exception:
        return "mock-token"

def custom_client_factory(headers=None, timeout=None, auth=None):
    dynamic_auth = DynamicGoogleAuth()
    return create_mcp_http_client(headers=headers, timeout=timeout, auth=dynamic_auth)

def create_mcp_toolset() -> LiveMcpToolset:
    return LiveMcpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=get_banking_service_mcp_url(),
            httpx_client_factory=custom_client_factory,
        )
    )

def end_consultation() -> dict:
    """Terminates the current voice consultation session. Call this when the customer confirms they are finished or want to end the call.
    """
    request_session_end()
    return {"status": "SUCCESS", "message": "Session end signal sent."}


def offer_session_closeout(tool_context: ToolContext) -> dict:
    """Open the final-assistance checkpoint before asking whether help is complete."""
    latest_turn = (latest_customer_turn_var.get() or {}).get("latest") or {}
    tool_context.state["closeout_checkpoint"] = open_closeout_checkpoint(
        originating_customer_event_id=str(latest_turn.get("event_id") or ""),
    )
    return {
        "success": True,
        "status": "CLOSEOUT_OFFERED",
        "customer_prompt": "Is there anything else I can help you with?",
        "model_instruction": (
            "Ask whether the customer needs anything else, then stop and wait for "
            "their next turn. Do not call end_consultation in this turn."
        ),
    }


def transfer_to_human(reason: str) -> dict:
    """Escalates the support session to a live human bank supervisor. Call this when the customer demands a human representative, disputes a fraud item that requires supervisor override, or when you are unable to resolve their request.
    
    Args:
        reason: The justification for escalating the call.
    """
    notify_event({"type": DataChannelEvent.HANDOFF_PENDING.value, "reason": reason})
    return {"status": "SUCCESS", "message": "Escalation sequence initiated."}


def prepare_customer_reported_fraud_confirmation(
    disputed_authorization_ids: list[str],
    disputed_transaction_ids: list[str],
    issue_replacement: bool,
    tool_context: ToolContext,
) -> dict:
    """Prepare an exact customer-reported fraud selection without mutating banking state."""
    state = tool_context.state
    playbook = dict(state.get("fraud_playbook") or {})
    if not playbook.get("open_alert_inspected") or playbook.get("fraud_alert_id"):
        return {
            "success": False,
            "error": "ACTIVE_ALERT_CHECK_REQUIRED",
            "message": "Confirm that no active fraud alert exists before preparing this report.",
        }

    recent_index = state.get("recent_transaction_index") or {}
    requested_authorization_ids = {
        str(value).strip()
        for value in disputed_authorization_ids
        if str(value).strip()
    }
    requested_transaction_ids = {
        str(value).strip() for value in disputed_transaction_ids if str(value).strip()
    }
    if not requested_authorization_ids and not requested_transaction_ids:
        return {
            "success": False,
            "error": "EMPTY_DISPUTE_SELECTION",
            "message": "Select at least one recent transaction before preparing confirmation.",
        }
    allowed_authorization_ids = {
        item_id
        for item_id, item in recent_index.items()
        if item.get("pending") is True
    }
    allowed_transaction_ids = {
        item_id
        for item_id, item in recent_index.items()
        if item.get("pending") is False and int(item.get("amount_cents") or 0) < 0
    }
    if requested_authorization_ids - allowed_authorization_ids:
        return {
            "success": False,
            "error": "INVALID_DISPUTED_AUTHORIZATION",
            "message": "One or more selected pending authorizations are not in the trusted recent history.",
        }
    if requested_transaction_ids - allowed_transaction_ids:
        return {
            "success": False,
            "error": "INVALID_DISPUTED_TRANSACTION",
            "message": "One or more selected posted transactions are not eligible entries in the trusted recent history.",
        }

    payload = {
        "disputed_authorization_ids": list(requested_authorization_ids),
        "disputed_transaction_ids": list(requested_transaction_ids),
        "issue_replacement": issue_replacement,
        "escalate": False,
    }
    existing = playbook.get("workflow_authorization") or {}
    if existing:
        playbook["last_workflow_authorization"] = invalidate_workflow_authorization(
            existing,
            reason="REPLACED_BY_NEW_CUSTOMER_REPORTED_SELECTION",
        )
    authorization = create_workflow_authorization(
        action=TRIAGE_CUSTOMER_REPORTED_FRAUD,
        payload=payload,
        session_id=str(state.get("session_id") or ""),
    )
    playbook.update(
        {
            "entry_mode": "CUSTOMER_REPORTED_FRAUD",
            "resolution_path": "CUSTOMER_REPORTED_FRAUD",
            "workflow_authorization": authorization,
        }
    )
    state["fraud_playbook"] = playbook
    return {
        "success": True,
        "confirmation_required": True,
        "action": TRIAGE_CUSTOMER_REPORTED_FRAUD,
        "payload": authorization["payload"],
        "payload_fingerprint": authorization["payload_fingerprint"],
        "selected_transactions": [
            {
                **recent_index[item_id],
                "amount_cents": recent_index[item_id].get("display_amount_cents"),
            }
            for item_id in sorted(requested_authorization_ids | requested_transaction_ids)
        ],
        "model_instruction": (
            "Restate the exact selected merchants and amounts, explain the pending-investigation actions, "
            "and ask for explicit confirmation. Do not call triage_customer_reported_fraud until a later customer turn confirms it."
        ),
    }


async def fetch_updated_account_details() -> dict:
    headers = {}
    token = get_auth_token_for_audience(BANKING_SERVICE_URL)
    headers["Authorization"] = f"Bearer {token}"
    headers["x-target-customer-id"] = active_customer_id_var.get()
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(f"{BANKING_SERVICE_URL}/api/credit-card/account", headers=headers)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
    return {}

def get_auth_headers() -> dict:
    token = get_auth_token_for_audience(BANKING_SERVICE_URL)
    return {
        "Authorization": f"Bearer {token}",
        "x-target-customer-id": active_customer_id_var.get()
    }

async def before_tool_callback(tool, args, tool_context, **kwargs) -> dict | None:
    tool_name = getattr(tool, "name", str(tool))
    import logging
    logger = logging.getLogger("voice_agent")
    fraud_context = tool_context.state.get("fraud_context", {}) if hasattr(tool_context, "state") else {}
    fraud_playbook = tool_context.state.get("fraud_playbook", {}) if hasattr(tool_context, "state") else {}
    if tool_name in LEGACY_DIRECT_ACTION_TOOLS:
        return {
            "success": False,
            "isError": False,
            "status": "LEGACY_DIRECT_ACTION_DISABLED",
            "action_completed": False,
            "message": "Use the typed proposal and commit tools for this action.",
        }
    if (
        tool_name == "offer_session_closeout"
        and (fraud_playbook.get("workflow_authorization") or {}).get("status")
        in {
            "PREPARED",
            "PENDING",
            "CONFIRMED",
            "EXECUTING",
            "RECOVERY_REQUIRED",
        }
    ):
        return {
            "success": False,
            "isError": False,
            "status": "PROPOSAL_DECISION_REQUIRED",
            "action_completed": False,
            "message": (
                "Resolve the current proposal with commit, decline, revise, "
                "or cancel before offering session closeout."
            ),
        }
    if tool_name == "end_consultation":
        block_reason = closeout_block_reason(
            closeout_checkpoint=tool_context.state.get("closeout_checkpoint"),
            workflow_authorization=fraud_playbook.get("workflow_authorization"),
            latest_customer_turn=(
                (latest_customer_turn_var.get() or {}).get("latest") or {}
            ),
        )
        if block_reason:
            fraud_playbook["completion_status"] = "ACTIVE"
            tool_context.state["fraud_playbook"] = fraud_playbook
            logger.info(
                "[CALLBACK] premature consultation close blocked %s",
                format_log_context(
                    state=tool_context.state,
                    tool_name=tool_name,
                    drift=block_reason,
                ),
            )
            return {
                "success": False,
                "isError": False,
                "status": "SESSION_CLOSE_CONFIRMATION_REQUIRED",
                "session_ended": False,
                "closeout_blocked": True,
                "required_action": block_reason,
                "message": "The voice support session is still active.",
                "customer_response": "Is there anything else I can help you with?",
                "model_instruction": (
                    "Do not say goodbye or claim the session ended. Call "
                    "offer_session_closeout, ask whether the customer needs anything "
                    "else, and wait for their next turn."
                ),
            }
    elif tool_name != "offer_session_closeout":
        checkpoint = tool_context.state.get("closeout_checkpoint")
        invalidated_checkpoint = invalidate_closeout_checkpoint(
            checkpoint,
            reason=f"INTERVENING_TOOL:{tool_name}",
        )
        if invalidated_checkpoint != (checkpoint or {}):
            tool_context.state["closeout_checkpoint"] = invalidated_checkpoint
    consequential_tools = {
        "unfreeze_card",
        "reverse_overdraft_fee",
        "request_credit_limit_increase",
        "resolve_fraud_alert",
        "commit_fraud_triage",
        "commit_card_reissue",
        "commit_wallet_provisioning",
        "triage_customer_reported_fraud",
    }
    if tool_name in consequential_tools:
        expected_generation = str(
            tool_context.state.get("reset_generation_token")
            or (tool_context.state.get("reset_generation") or {}).get("token")
            or ""
        )
        try:
            reset_headers = get_auth_headers()
        except Exception:
            reset_headers = {}
        generation_valid, generation_reason = await validate_reset_generation(
            banking_service_url=BANKING_SERVICE_URL,
            headers=reset_headers,
            expected_token=expected_generation,
        )
        if not generation_valid:
            logger.warning(
                "[CALLBACK] reset generation blocked consequential tool %s",
                format_log_context(
                    state=tool_context.state,
                    tool_name=tool_name,
                    drift=generation_reason,
                ),
            )
            return {
                "success": False,
                "isError": True,
                "error": "SESSION_INVALIDATED",
                "message": "This consultation is no longer current because demo data changed. Start a new consultation before taking action.",
                "required_action": generation_reason,
                "model_instruction": "Do not claim success or retry this tool in the current session.",
            }
    active_authorization = fraud_playbook.get("workflow_authorization") or {}
    if active_authorization.get("status") in {
        "PREPARED",
        "PENDING",
        "CONFIRMED",
        "EXECUTING",
        "RECOVERY_REQUIRED",
    }:
        if tool_name in PROPOSAL_ACTION_BY_TOOL:
            return {
                "success": False,
                "isError": False,
                "status": "PROPOSAL_DECISION_REQUIRED",
                "action_completed": False,
                "message": (
                    "Record REVISE or CANCEL for the current proposal before "
                    "creating a replacement proposal."
                ),
            }
        if tool_name == "review_fraud_selection":
            return {
                "success": False,
                "isError": False,
                "status": "PROPOSAL_REVISION_REQUIRED",
                "action_completed": False,
                "message": (
                    "Record REVISE for the current proposal before changing "
                    "the fraud selection."
                ),
            }
    authorization_action = COMMIT_ACTION_BY_TOOL.get(tool_name)
    if tool_name == "decide_action_proposal":
        authorization_action = active_authorization.get("action")
    if tool_name == "triage_customer_reported_fraud":
        authorization_action = TRIAGE_CUSTOMER_REPORTED_FRAUD
    authorization_to_execute = None
    if authorization_action:
        authorization = fraud_playbook.get("workflow_authorization") or {}
        if (
            tool_name == "decide_action_proposal"
            and authorization.get("status") == "RECOVERY_REQUIRED"
        ):
            return {
                "success": False,
                "isError": False,
                "status": "COMMIT_RECOVERY_REQUIRED",
                "action_completed": False,
                "message": (
                    "The prior commit result is unresolved. Retry the same commit "
                    "or transfer to a specialist before another proposal decision."
                ),
            }
        validation_payload = (
            authorization.get("payload")
            if tool_name in PROPOSAL_DECISION_TOOLS
            else args
        )
        if (
            tool_name in PROPOSAL_DECISION_TOOLS
            and authorization.get("status") == "PENDING"
        ):
            latest_turn = (latest_customer_turn_var.get() or {}).get("latest") or {}
            authorization = authorize_from_model_tool_intent(
                authorization,
                action=authorization_action,
                payload=validation_payload,
                session_id=str(tool_context.state.get("session_id") or ""),
                customer_event_id=str(latest_turn.get("event_id") or ""),
                customer_observed_at_epoch_s=float(
                    latest_turn.get("observed_at_epoch_s") or 0
                ),
            )
            fraud_playbook["workflow_authorization"] = authorization
            tool_context.state["fraud_playbook"] = fraud_playbook
        authorization_error = validate_workflow_authorization(
            authorization,
            action=authorization_action,
            payload=validation_payload,
            session_id=str(tool_context.state.get("session_id") or ""),
        )
        if (
            not authorization_error
            and tool_name in PROPOSAL_DECISION_TOOLS
            and str(args.get("proposal_id") or "") != str(authorization.get("proposal_id") or "")
        ):
            authorization_error = (
                "The proposal id differs from the exact current banking proposal."
            )
        if authorization_error:
            logger.warning(
                "[CALLBACK] workflow authorization blocked %s",
                format_log_context(
                    state=tool_context.state,
                    tool_name=tool_name,
                    drift=authorization_error,
                ),
            )
            blocked_result = {
                "success": False,
                "isError": False,
                "status": "AUTHORIZATION_REQUIRED",
                "action_completed": False,
                "message": "The action has not run because customer confirmation is still required.",
                "authorization_blocked": True,
                "required_action": authorization_error,
                "model_instruction": (
                    "This is an expected authorization checkpoint, not a technical failure. "
                    "The action DID NOT RUN. Do not say it completed, was added, or was queued, "
                    "and do not end the consultation. If the exact selection is already prepared, "
                    "restate it and ask the customer for explicit confirmation, then stop and wait. "
                    "Otherwise prepare it first."
                ),
            }
            if tool_name == "commit_wallet_provisioning":
                blocked_result.update(
                    {
                        "wallet_provisioning_status": "NOT_QUEUED",
                        "customer_response": (
                            "I have not queued the card yet. Please say yes if you want "
                            "me to queue it for Google Wallet."
                        ),
                    }
                )
            return blocked_result
        authorization_to_execute = authorization
    if tool_name == "transfer_to_human":
        fraud_playbook["escalation_status"] = "EXECUTING"
        fraud_playbook["escalation_reason"] = str(args.get("reason") or "").strip()
        tool_context.state["fraud_playbook"] = fraud_playbook
    elif tool_name == "end_consultation":
        fraud_playbook["completion_status"] = "ENDING"
        tool_context.state["fraud_playbook"] = fraud_playbook
    logger.info(
        "[CALLBACK] before_tool_callback triggered %s args=%s",
        format_log_context(
            state=tool_context.state if hasattr(tool_context, "state") else None,
            tool_name=tool_name,
        ),
        tool_args_log_summary(tool_name, args),
    )
    logger.debug(
        "[CALLBACK] fraud callback state fraud_alert_present=%s playbook_keys=%s",
        bool(fraud_context.get("fraud_alert_id")),
        sorted(fraud_playbook.keys()),
    )
    mitigation_tools = {
        "resolve_fraud_alert",
        "commit_fraud_triage",
        "commit_card_reissue",
        "commit_wallet_provisioning",
        "triage_customer_reported_fraud",
    }
    sequencing_args = (
        (authorization_to_execute or {}).get("payload", {})
        if tool_name in PROPOSAL_DECISION_TOOLS
        else args
    )
    sequencing_error = validate_fraud_tool_sequence(
        fraud_playbook, tool_name, sequencing_args
    )
    if sequencing_error:
        logger.warning(
            "[CALLBACK] fraud playbook drift %s",
            format_log_context(
                state=tool_context.state if hasattr(tool_context, "state") else None,
                tool_name=tool_name,
                drift=sequencing_error,
            ),
        )
        return {
            "success": False,
            "isError": True,
            "error": "ACTION_NOT_COMPLETED",
            "message": f"Action not completed. {sequencing_error}",
            "sequence_blocked": True,
            "required_action": sequencing_error,
            "model_instruction": "Do not tell the customer this action succeeded. Follow required_action before retrying.",
        }
    if (
        fraud_playbook.get("must_inspect_open_alert_first")
        and not fraud_playbook.get("open_alert_inspected")
        and tool_name in mitigation_tools
    ):
        logger.warning(
            "[CALLBACK] fraud playbook drift %s",
            format_log_context(
                state=tool_context.state if hasattr(tool_context, "state") else None,
                tool_name=tool_name,
                drift="mitigation_tool_invoked_before_open_alert_inspection",
            ),
        )
    if authorization_to_execute:
        if tool_name == "decide_action_proposal":
            fraud_playbook["workflow_authorization"] = authorization_to_execute
        else:
            fraud_playbook["workflow_authorization"] = mark_authorization_executing(
                authorization_to_execute
            )
        if tool_name in PROPOSAL_DECISION_TOOLS:
            holder = proposal_runtime_context_var.get()
            if holder is not None:
                holder["confirmation"] = {
                    "presentation_turn_id": authorization_to_execute.get("assistant_event_id"),
                    "confirmation_turn_id": authorization_to_execute.get("customer_event_id"),
                }
        if tool_name == "triage_customer_reported_fraud":
            action = (
                TRIAGE_CUSTOMER_REPORTED_FRAUD
            )
            args["idempotency_key"] = (
                f"voice:{tool_context.state.get('session_id')}:triage:"
                f"{action_payload_fingerprint(action, args)[:24]}"
            )
        tool_context.state["fraud_playbook"] = fraud_playbook
    set_tool_processing(True)
    tool_context.state["is_processing_tool"] = True
    tool_started = dict(tool_context.state.get("_voice_tool_started_at") or {})
    tool_started[tool_name] = time.monotonic()
    tool_context.state["_voice_tool_started_at"] = tool_started
    return None

async def on_tool_error_callback(tool, args, tool_context, error, **kwargs) -> None:
    tool_name = getattr(tool, "name", str(tool))
    if tool_name in PROPOSAL_DECISION_TOOLS:
        holder = proposal_runtime_context_var.get()
        if holder is not None:
            holder["confirmation"] = None
    import logging
    logger = logging.getLogger("voice_agent")
    logger.error(
        "[CALLBACK] on_tool_error_callback triggered %s error=%s args=%s",
        format_log_context(
            state=tool_context.state if hasattr(tool_context, "state") else None,
            tool_name=tool_name,
        ),
        type(error).__name__,
        tool_args_log_summary(tool_name, args),
    )
    set_tool_processing(False)
    tool_context.state["is_processing_tool"] = False
    tool_started = dict(tool_context.state.get("_voice_tool_started_at") or {})
    started_at = tool_started.pop(tool_name, time.monotonic())
    tool_context.state["_voice_tool_started_at"] = tool_started
    duration_seconds = time.monotonic() - started_at
    record_tool_completed(tool_name, "error", duration_seconds)
    if tool_name in PROPOSAL_DECISION_TOOLS:
        _record_commit_proposal_event(
            state=tool_context.state,
            tool_name=tool_name,
            args=args,
            result={"error": type(error).__name__},
            outcome="TOOL_ERROR",
            latency_ms=duration_seconds * 1000,
        )
    notify_event(
        {
            "type": INTERNAL_TOOL_RUNTIME_STATUS,
            "tool": tool_name,
            "outcome": "error",
        }
    )
    playbook = dict(tool_context.state.get("fraud_playbook") or {})
    authorization = playbook.get("workflow_authorization") or {}
    if (
        tool_name in AUTHORIZATION_EXECUTION_TOOLS
        and authorization.get("status") == "EXECUTING"
    ):
        playbook["workflow_authorization"] = mark_authorization_recovery_required(
            authorization,
            reason=f"TOOL_ERROR:{tool_name}",
        )
        tool_context.state["fraud_playbook"] = playbook
    if tool_name == "transfer_to_human":
        playbook["escalation_status"] = "FAILED"
        tool_context.state["fraud_playbook"] = playbook
    elif tool_name == "end_consultation":
        playbook["completion_status"] = "END_FAILED"
        tool_context.state["fraud_playbook"] = playbook
    return None

async def after_tool_callback(tool, args, tool_context, tool_response, **kwargs) -> dict | None:
    tool_name = getattr(tool, "name", str(tool))
    if tool_name in PROPOSAL_DECISION_TOOLS:
        holder = proposal_runtime_context_var.get()
        if holder is not None:
            holder["confirmation"] = None
    import logging
    logger = logging.getLogger("voice_agent")
    logger.info(
        "[CALLBACK] after_tool_callback triggered %s result=%s",
        format_log_context(
            state=tool_context.state if hasattr(tool_context, "state") else None,
            tool_name=tool_name,
        ),
        tool_result_log_summary(tool_response),
    )
    set_tool_processing(False)
    tool_context.state["is_processing_tool"] = False
    # Check if the tool succeeded
    structured = tool_response.get("structuredContent") if isinstance(tool_response, dict) else None
    success = tool_response_succeeded(tool_name, tool_response)
    expected_checkpoint = tool_response_is_expected_checkpoint(tool_response)
    outcome = "checkpoint" if expected_checkpoint else (
        "success" if success else "failure"
    )
    tool_started = dict(tool_context.state.get("_voice_tool_started_at") or {})
    started_at = tool_started.pop(tool_name, time.monotonic())
    tool_context.state["_voice_tool_started_at"] = tool_started
    duration_seconds = time.monotonic() - started_at
    record_tool_completed(
        tool_name,
        outcome,
        duration_seconds,
    )
    if tool_name in PROPOSAL_DECISION_TOOLS:
        _record_commit_proposal_event(
            state=tool_context.state,
            tool_name=tool_name,
            args=args,
            result=structured if isinstance(structured, dict) else None,
            outcome=outcome,
            latency_ms=duration_seconds * 1000,
        )
    if isinstance(structured, dict):
        guidance = structured.get("support_guidance")
        if isinstance(guidance, dict) and guidance:
            tool_context.state["support_guidance"] = guidance
            notify_event(
                {
                    "type": DataChannelEvent.GUIDANCE_SNAPSHOT.value,
                    **guidance_observability_payload(guidance),
                }
            )
        proposal_action = PROPOSAL_ACTION_BY_TOOL.get(tool_name)
        if proposal_action and structured.get("success") is True:
            playbook = dict(tool_context.state.get("fraud_playbook") or {})
            existing = playbook.get("workflow_authorization") or {}
            if existing:
                playbook["last_workflow_authorization"] = (
                    invalidate_workflow_authorization(
                        existing,
                        reason="REPLACED_BY_NEW_ACTION_PROPOSAL",
                    )
                )
            authorization = create_workflow_authorization(
                action=proposal_action,
                payload=args,
                session_id=str(tool_context.state.get("session_id") or ""),
                originating_customer_event_id=str(
                    (
                        (latest_customer_turn_var.get() or {}).get("latest") or {}
                    ).get("event_id")
                    or ""
                ),
            )
            authorization.update(
                {
                    "proposal_id": str(structured.get("proposal_id") or ""),
                    "contract_version": str(
                        structured.get("contract_version") or ""
                    ),
                    "customer_safe_summary": str(
                        structured.get("customer_safe_summary") or ""
                    ),
                }
            )
            playbook["workflow_authorization"] = authorization
            tool_context.state["fraud_playbook"] = playbook
            runtime_context = proposal_runtime_context_var.get() or {}
            record_action_proposal_event(
                runtime=str(
                    runtime_context.get("runtime_name") or "ADK_GEMINI_LIVE"
                ),
                support_session_id=str(
                    runtime_context.get("support_session_id")
                    or tool_context.state.get("session_id")
                    or ""
                ),
                proposal_id=authorization.get("proposal_id"),
                contract_version=authorization.get("contract_version"),
                catalog_snapshot_id=runtime_context.get("catalog_snapshot_id"),
                tool=tool_name,
                outcome="PROPOSED",
                latency_ms=duration_seconds * 1000,
            )
        if tool_name == "review_fraud_selection" and structured.get("success") is True:
            playbook = dict(tool_context.state.get("fraud_playbook") or {})
            previous_review = playbook.get("fraud_review") or {}
            review = {
                "stage": structured.get("stage"),
                "selection_status": structured.get("selection_status"),
                "selection_fingerprint": structured.get("selection_fingerprint"),
                "ready_to_propose": bool(structured.get("ready_to_propose")),
                "remaining_item_count": structured.get("remaining_item_count"),
                "disputed_authorization_ids": structured.get(
                    "disputed_authorization_ids", []
                ),
                "disputed_transaction_ids": structured.get(
                    "disputed_transaction_ids", []
                ),
                "recognized_authorization_ids": structured.get(
                    "recognized_authorization_ids", []
                ),
                "recognized_transaction_ids": structured.get(
                    "recognized_transaction_ids", []
                ),
            }
            if (
                previous_review.get("selection_fingerprint")
                and previous_review.get("selection_fingerprint")
                != review.get("selection_fingerprint")
            ):
                authorization = playbook.get("workflow_authorization") or {}
                if authorization:
                    playbook["last_workflow_authorization"] = (
                        invalidate_workflow_authorization(
                            authorization,
                            reason="FRAUD_SELECTION_CHANGED",
                        )
                    )
                    playbook["workflow_authorization"] = None
            playbook["fraud_review"] = review
            tool_context.state["fraud_playbook"] = playbook
            logger.info(
                "[FRAUD_REVIEW] stage=%s status=%s ready=%s remaining=%s",
                review.get("stage"),
                review.get("selection_status"),
                review.get("ready_to_propose"),
                review.get("remaining_item_count"),
            )
        if (
            tool_name == "decide_action_proposal"
            and structured.get("success") is True
        ):
            playbook = dict(tool_context.state.get("fraud_playbook") or {})
            authorization = dict(playbook.get("workflow_authorization") or {})
            authorization["status"] = str(structured.get("status") or "")
            authorization["invalidation_reason"] = structured.get(
                "invalidation_reason"
            )
            authorization["decision"] = str(structured.get("decision") or "")
            playbook["workflow_authorization"] = authorization
            tool_context.state["fraud_playbook"] = playbook
        if tool_name == "get_open_fraud_alert" and structured.get("fraud_alert") is None:
            playbook = dict(tool_context.state.get("fraud_playbook") or {})
            playbook["open_alert_inspected"] = True
            playbook["fraud_alert_id"] = None
            tool_context.state["fraud_playbook"] = playbook
        if tool_name == "get_transaction_history" and structured.get("success") is True:
            recent_index = {}
            for item in (structured.get("data") or [])[:50]:
                item_id = item.get("authorization_id") or item.get("transaction_id") or item.get("id")
                if not item_id:
                    continue
                recent_index[str(item_id)] = {
                    "id": str(item_id),
                    "description": item.get("description"),
                    "amount_cents": item.get("amount_cents"),
                    "display_amount_cents": abs(int(item.get("amount_cents") or 0)),
                    "pending": bool(item.get("pending")),
                    "posted_at": item.get("posted_at") or item.get("timestamp"),
                    "last_four": item.get("last_four"),
                }
            tool_context.state["recent_transaction_index"] = recent_index
    notify_event(
        {
            "type": INTERNAL_TOOL_RUNTIME_STATUS,
            "tool": tool_name,
            "outcome": outcome,
        }
    )
    if isinstance(tool_response, dict) and tool_response.get("status") == "SUCCESS":
        playbook = dict(tool_context.state.get("fraud_playbook") or {})
        if tool_name == "transfer_to_human":
            playbook["escalation_status"] = "COMPLETED"
        elif tool_name == "end_consultation":
            playbook["completion_status"] = "COMPLETED"
        tool_context.state["fraud_playbook"] = playbook
    if structured and isinstance(structured, dict) and structured.get("success") is True:
        authorization = (
            tool_context.state.get("fraud_playbook", {}).get("workflow_authorization")
        )
        if authorization and authorization.get("status") == "EXECUTING":
            completed_playbook = dict(tool_context.state.get("fraud_playbook") or {})
            completed_playbook["workflow_authorization"] = mark_authorization_completed(
                authorization
            )
            tool_context.state["fraud_playbook"] = completed_playbook
        updated_playbook = mark_fraud_tool_completed(
            tool_context.state.get("fraud_playbook", {}),
            tool_name,
            structured,
        )
        if updated_playbook:
            tool_context.state["fraud_playbook"] = updated_playbook

        if tool_name == "get_open_fraud_alert":
            fraud_alert = structured.get("fraud_alert") or {}
            logger.info(
                "[CALLBACK] fraud playbook inspection completed %s",
                format_log_context(
                    state=tool_context.state if hasattr(tool_context, "state") else None,
                    tool_name=tool_name,
                    suspicious_transactions_count=len(fraud_alert.get("suspicious_transactions") or []),
                ),
            )
            notify_event({
                "type": DataChannelEvent.FRAUD_ALERT_INSPECTED.value,
                "fraud_alert_id": fraud_alert.get("fraud_alert_id"),
                "card_last_four": fraud_alert.get("card_last_four"),
                "status": fraud_alert.get("status"),
                "suspicious_transactions_count": len(fraud_alert.get("suspicious_transactions") or []),
            })

        if tool_name == "resolve_fraud_alert":
            logger.info(
                "[CALLBACK] FRAUD_ALERT_RESOLVED event broadcasted %s",
                format_log_context(
                    state=tool_context.state if hasattr(tool_context, "state") else None,
                    tool_name=tool_name,
                    resolution=(structured.get("fraud_alert") or {}).get("resolution"),
                ),
            )
            fraud_alert = structured.get("fraud_alert") or {}
            notify_event({
                "type": DataChannelEvent.FRAUD_ALERT_RESOLVED.value,
                "fraud_alert_id": fraud_alert.get("fraud_alert_id"),
                "status": fraud_alert.get("status"),
                "resolution": fraud_alert.get("resolution"),
                "card_last_four": fraud_alert.get("card_last_four"),
            })
            return None

        if tool_name in {
            "commit_fraud_triage",
            "triage_customer_reported_fraud",
        }:
            logger.info(
                "[CALLBACK] FRAUD_CASE_TRIAGED event broadcasted %s",
                format_log_context(
                    state=tool_context.state if hasattr(tool_context, "state") else None,
                    tool_name=tool_name,
                    outcome=structured.get("outcome"),
                ),
            )
            fraud_alert = structured.get("fraud_alert") or {}
            notify_event({
                "type": DataChannelEvent.FRAUD_ALERT_RESOLVED.value,
                "fraud_alert_id": fraud_alert.get("fraud_alert_id"),
                "status": fraud_alert.get("status"),
                "resolution": structured.get("outcome"),
                "card_last_four": fraud_alert.get("card_last_four"),
                "voided_authorizations": structured.get("voided_authorizations", []),
                "provisional_credits": structured.get("provisional_credits", []),
                "replacement_card": structured.get("replacement_card"),
                "secure_message": structured.get("secure_message"),
                "escalated": structured.get("escalated", False),
            })
            return build_triage_model_result(structured)

        if tool_name == "commit_card_reissue":
            replacement = structured.get("replacement_card") or {}
            notify_event(
                {
                    "type": DataChannelEvent.CARD_REPLACED.value,
                    "replacement_status": replacement.get(
                        "replacement_status", "ISSUED"
                    ),
                    "status": replacement.get("status", "ACTIVE"),
                    "new_last_four": replacement.get("new_last_four"),
                    "card_token": replacement.get("new_card_token"),
                    "is_virtual": replacement.get("is_virtual", True),
                }
            )
        elif tool_name == "commit_wallet_provisioning":
            notify_event(
                {
                    "type": DataChannelEvent.WALLET_PROVISIONING_QUEUED.value,
                    "wallet_provider": structured.get(
                        "wallet_provider", "GOOGLE_WALLET"
                    ),
                    "wallet_provisioning_status": structured.get(
                        "wallet_provisioning_status", "QUEUED"
                    ),
                    "card_token": structured.get("card_token"),
                }
            )

        account_data = await fetch_updated_account_details()
        logger.info(
            "[CALLBACK] fetch_updated_account_details returned %s account_loaded=%s",
            format_log_context(
                state=tool_context.state if hasattr(tool_context, "state") else None,
                tool_name=tool_name,
            ),
            bool(account_data),
        )
        if account_data:
            if tool_name == "request_credit_limit_increase" or tool_name == "request_limit_increase":
                logger.info("[CALLBACK] LIMIT_UPDATED event broadcasted %s", format_log_context(state=tool_context.state if hasattr(tool_context, "state") else None, tool_name=tool_name))
                notify_event({
                    "type": DataChannelEvent.LIMIT_UPDATED.value,
                    "credit_limit_cents": account_data.get("credit_limit_cents"),
                    "available_credit_cents": account_data.get("available_credit_cents")
                })
            elif tool_name == "reverse_overdraft_fee" or tool_name == "reverse_posted_fee":
                logger.info("[CALLBACK] FEE_REVERSED event broadcasted %s", format_log_context(state=tool_context.state if hasattr(tool_context, "state") else None, tool_name=tool_name))
                notify_event({
                    "type": DataChannelEvent.FEE_REVERSED.value,
                    "cleared_balance_cents": account_data.get("cleared_balance_cents"),
                    "available_credit_cents": account_data.get("available_credit_cents")
                })
            elif tool_name == "block_card_instrument":
                logger.info("[CALLBACK] CARD_STATUS_LOCK event broadcasted %s", format_log_context(state=tool_context.state if hasattr(tool_context, "state") else None, tool_name=tool_name))
                notify_event({
                    "type": DataChannelEvent.CARD_STATUS_LOCK.value,
                    "status": "BLOCKED"
                })
    else:
        playbook = dict(tool_context.state.get("fraud_playbook") or {})
        authorization = playbook.get("workflow_authorization") or {}
        if (
            tool_name in AUTHORIZATION_EXECUTION_TOOLS
            and authorization.get("status") == "EXECUTING"
        ):
            playbook["workflow_authorization"] = mark_authorization_recovery_required(
                authorization,
                reason=f"TOOL_RESULT_NOT_SUCCESSFUL:{tool_name}",
            )
            tool_context.state["fraud_playbook"] = playbook
    return None

NAME = "credit_card_support_voice_assistant"
DESCRIPTION = "A voice assistant that helps customers freeze cards, issue replacement cards, request limit increases, and reverse late fees."


def create_voice_agent(*, model=None, instruction: str = INSTRUCTION_TEXT) -> Agent:
    return Agent(
        name=NAME,
        description=DESCRIPTION,
        model=model or os.getenv("VOICE_AGENT_AUDIO_MODEL"),
        instruction=instruction,
        tools=[
            create_mcp_toolset(),
            prepare_customer_reported_fraud_confirmation,
            offer_session_closeout,
            end_consultation,
            transfer_to_human,
        ],
        before_tool_callback=before_tool_callback,
        after_tool_callback=after_tool_callback,
        on_tool_error_callback=on_tool_error_callback,
        planner=BuiltInPlanner(
            thinking_config=ThinkingConfig(include_thoughts=False)
        )
    )

root_agent = None
