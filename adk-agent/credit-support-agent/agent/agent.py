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
import google
import httpx
from google.adk.agents import Agent
from google.adk.planners import BuiltInPlanner
from google.genai.types import ThinkingConfig
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams, create_mcp_http_client

from agent.events import DataChannelEvent

LOCATION = os.getenv("LOCATION", "us-central1")
credentials, project_id = google.auth.default()
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project_id)
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", LOCATION)
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")

BANKING_SERVICE_URL = os.getenv("BANKING_SERVICE_URL", "http://localhost:8080").rstrip("/")
active_customer_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("active_customer_id", default="jane.doe@example.com")
session_event_callback_var: contextvars.ContextVar = contextvars.ContextVar("session_event_callback", default=None)
session_should_end_var: contextvars.ContextVar[bool] = contextvars.ContextVar("session_should_end", default=False)
is_processing_tool_var: contextvars.ContextVar[bool] = contextvars.ContextVar("is_processing_tool", default=False)

def register_event_callback(cb):
    session_event_callback_var.set(cb)


def bind_session_context(customer_id: str, callback):
    """Binds per-session customer and callback context and resets transient flags."""
    return {
        "customer": active_customer_id_var.set(customer_id),
        "callback": session_event_callback_var.set(callback),
        "should_end": session_should_end_var.set(False),
        "is_processing": is_processing_tool_var.set(False),
    }


def reset_session_context(tokens: dict) -> None:
    """Restores prior context-var state for a completed session."""
    if not tokens:
        return
    is_processing_tool_var.reset(tokens["is_processing"])
    session_should_end_var.reset(tokens["should_end"])
    session_event_callback_var.reset(tokens["callback"])
    active_customer_id_var.reset(tokens["customer"])


def is_session_end_requested() -> bool:
    return session_should_end_var.get()


def request_session_end() -> None:
    session_should_end_var.set(True)


def clear_session_end_request() -> None:
    session_should_end_var.set(False)


def is_tool_processing() -> bool:
    return is_processing_tool_var.get()


def set_tool_processing(is_processing: bool) -> None:
    is_processing_tool_var.set(is_processing)

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

# Initialize MCP Toolset using Streamable HTTP
mcp_tools = McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url=f"{BANKING_SERVICE_URL}/api/mcp/",
        httpx_client_factory=custom_client_factory
    )
)

def end_consultation() -> dict:
    """Terminates the current voice consultation session. Call this when the customer confirms they are finished or want to end the call.
    """
    request_session_end()
    return {"status": "SUCCESS", "message": "Session end signal sent."}

def transfer_to_human(reason: str) -> dict:
    """Escalates the support session to a live human bank supervisor. Call this when the customer demands a human representative, disputes a fraud item that requires supervisor override, or when you are unable to resolve their request.
    
    Args:
        reason: The justification for escalating the call.
    """
    notify_event({"type": DataChannelEvent.HANDOFF_PENDING.value, "reason": reason})
    return {"status": "SUCCESS", "message": "Escalation sequence initiated."}

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

async def before_tool_callback(tool, args, tool_context, **kwargs) -> None:
    tool_name = getattr(tool, "name", str(tool))
    import logging
    logger = logging.getLogger("voice_agent")
    logger.info(f"[CALLBACK] before_tool_callback triggered: tool_name={tool_name}, args={args}")
    set_tool_processing(True)
    tool_context.state["is_processing_tool"] = True
    return None

async def on_tool_error_callback(tool, args, tool_context, error, **kwargs) -> None:
    tool_name = getattr(tool, "name", str(tool))
    import logging
    logger = logging.getLogger("voice_agent")
    logger.info(f"[CALLBACK] on_tool_error_callback triggered: tool_name={tool_name}, error={error}")
    set_tool_processing(False)
    tool_context.state["is_processing_tool"] = False
    return None

async def after_tool_callback(tool, args, tool_context, tool_response, **kwargs) -> dict | None:
    tool_name = getattr(tool, "name", str(tool))
    import logging
    logger = logging.getLogger("voice_agent")
    logger.info(f"[CALLBACK] after_tool_callback triggered: tool_name={tool_name}, result={tool_response}")
    set_tool_processing(False)
    tool_context.state["is_processing_tool"] = False
    # Check if the tool succeeded
    structured = tool_response.get("structuredContent") if isinstance(tool_response, dict) else None
    if structured and isinstance(structured, dict) and structured.get("success") is True:
        if tool_name == "resolve_fraud_alert":
            logger.info("[CALLBACK] FRAUD_ALERT_RESOLVED event broadcasted")
            fraud_alert = structured.get("fraud_alert") or {}
            notify_event({
                "type": DataChannelEvent.FRAUD_ALERT_RESOLVED.value,
                "fraud_alert_id": fraud_alert.get("fraud_alert_id"),
                "status": fraud_alert.get("status"),
                "resolution": fraud_alert.get("resolution"),
                "card_last_four": fraud_alert.get("card_last_four"),
            })
            return None

        account_data = await fetch_updated_account_details()
        logger.info(f"[CALLBACK] fetch_updated_account_details returned: {account_data}")
        if account_data:
            if tool_name == "request_credit_limit_increase" or tool_name == "request_limit_increase":
                logger.info("[CALLBACK] LIMIT_UPDATED event broadcasted")
                notify_event({
                    "type": DataChannelEvent.LIMIT_UPDATED.value,
                    "credit_limit_cents": account_data.get("credit_limit_cents"),
                    "available_credit_cents": account_data.get("available_credit_cents")
                })
            elif tool_name == "reverse_overdraft_fee" or tool_name == "reverse_posted_fee":
                logger.info("[CALLBACK] FEE_REVERSED event broadcasted")
                notify_event({
                    "type": DataChannelEvent.FEE_REVERSED.value,
                    "cleared_balance_cents": account_data.get("cleared_balance_cents"),
                    "available_credit_cents": account_data.get("available_credit_cents")
                })
            elif tool_name == "report_lost_stolen_card" or tool_name == "block_card_instrument":
                logger.info("[CALLBACK] CARD_STATUS_LOCK event broadcasted")
                notify_event({
                    "type": DataChannelEvent.CARD_STATUS_LOCK.value,
                    "status": "BLOCKED"
                })
            elif tool_name == "issue_replacement_card_tool":
                logger.info("[CALLBACK] CARD_REPLACED event broadcasted")
                first_card = (account_data.get("cards") or [{}])[0]
                notify_event({
                    "type": DataChannelEvent.CARD_REPLACED.value,
                    "status": first_card.get("status", "ACTIVE"),
                    "new_last_four": first_card.get("last_four"),
                    "card_token": first_card.get("card_token"),
                    "is_virtual": first_card.get("is_virtual", True),
                })
            elif tool_name == "push_card_to_google_wallet":
                logger.info("[CALLBACK] WALLET_PROVISIONING_QUEUED event broadcasted")
                notify_event({
                    "type": DataChannelEvent.WALLET_PROVISIONING_QUEUED.value,
                    "wallet_provider": structured.get("wallet_provider", "GOOGLE_WALLET"),
                    "wallet_provisioning_status": structured.get("wallet_provisioning_status", "QUEUED"),
                    "card_token": structured.get("card_token"),
                    "fraud_alert_id": structured.get("fraud_alert_id"),
                })
    return None

NAME = "credit_card_support_voice_assistant"
DESCRIPTION = "A voice assistant that helps customers freeze cards, issue replacement cards, request limit increases, and reverse late fees."

INSTRUCTION_PATH = os.path.join(os.path.dirname(__file__), "resources", "instruction.txt")
with open(INSTRUCTION_PATH, "r", encoding="utf-8") as f:
    INSTRUCTION_TEXT = f.read()

root_agent = Agent(
    name=NAME,
    description=DESCRIPTION,
    model=os.getenv("VOICE_AGENT_AUDIO_MODEL"),
    instruction=INSTRUCTION_TEXT,
    tools=[mcp_tools, end_consultation, transfer_to_human],
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
    on_tool_error_callback=on_tool_error_callback,
    planner=BuiltInPlanner(
        thinking_config=ThinkingConfig(include_thoughts=False)
    )
)
