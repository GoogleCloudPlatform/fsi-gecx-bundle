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
import asyncio
import google
import httpx
from google.adk.agents import Agent
from google.adk.planners import BuiltInPlanner
from google.genai.types import ThinkingConfig

from agent.events import DataChannelEvent

LOCATION = os.getenv("LOCATION", "us-central1")
credentials, project_id = google.auth.default()
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project_id)
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", LOCATION)
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")

BANKING_SERVICE_URL = os.getenv("BANKING_SERVICE_URL", "http://localhost:8080").rstrip("/")
ACTIVE_CUSTOMER_ID = "cust-123"

# Event broker for publishing tool execution status updates to LiveKit data channel
EVENT_CALLBACKS = []

def register_event_callback(cb):
    EVENT_CALLBACKS.append(cb)

def notify_event(event_dict):
    for cb in EVENT_CALLBACKS:
        try:
            cb(event_dict)
        except Exception as e:
            pass

def get_auth_headers() -> dict:
    """Fetches OIDC ID token for service-to-service authentication."""
    if os.getenv("ENV") == "development" or os.getenv("ALLOW_DEV_AUTH_BYPASS") == "true":
        return {"Authorization": "Bearer mock-token"}
    
    try:
        import google.auth.transport.requests
        import google.oauth2.id_token
        auth_req = google.auth.transport.requests.Request()
        # Fetch ID token using the base banking service URL as audience
        token = google.oauth2.id_token.fetch_id_token(auth_req, BANKING_SERVICE_URL)
        return {"Authorization": f"Bearer {token}"}
    except Exception as e:
        return {"Authorization": "Bearer mock-token"}

# Custom tools wrapped with docstrings for the LLM planner
async def block_credit_card(reason: str) -> dict:
    """Permanently blocks the active customer's primary credit card by setting its status to 'BLOCKED'.
    
    Args:
        reason: The reason for blocking the card (e.g. 'lost', 'stolen').
    """
    headers = get_auth_headers()
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # 1. Fetch account info to locate active card token
            account_url = f"{BANKING_SERVICE_URL}/credit-card/account"
            params = {"target_customer_id": ACTIVE_CUSTOMER_ID}
            resp = await client.get(account_url, params=params, headers=headers)
            if resp.status_code != 200:
                return {"status": "ERROR", "message": f"Failed to get account details: {resp.text}"}
            
            account_data = resp.json()
            cards = account_data.get("cards", [])
            active_card = next((c for c in cards if c.get("status") == "ACTIVE"), None)
            if not active_card:
                return {"status": "ERROR", "message": "No active credit card found for this account."}
            
            # 2. Block the card
            block_url = f"{BANKING_SERVICE_URL}/credit-card/block"
            block_params = {
                "card_token": active_card["card_token"],
                "target_customer_id": ACTIVE_CUSTOMER_ID
            }
            resp_block = await client.post(block_url, params=block_params, headers=headers)
            if resp_block.status_code != 200:
                return {"status": "ERROR", "message": f"Failed to block card: {resp_block.text}"}
            
            notify_event({"type": DataChannelEvent.CARD_STATUS_LOCK.value, "status": "BLOCKED"})
            return {"status": "SUCCESS", "message": "Card successfully blocked.", "data": resp_block.json().get("data")}
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

async def apply_limit_increase(requested_limit_cents: int) -> dict:
    """Updates the credit line limit for the active customer's account.
    
    Args:
        requested_limit_cents: The new credit limit in cents (e.g., 1200000 cents for $12,000 limit).
    """
    headers = get_auth_headers()
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            limit_url = f"{BANKING_SERVICE_URL}/credit-card/limit"
            params = {
                "requested_limit_cents": requested_limit_cents,
                "target_customer_id": ACTIVE_CUSTOMER_ID
            }
            resp = await client.post(limit_url, params=params, headers=headers)
            if resp.status_code != 200:
                return {"status": "ERROR", "message": f"Failed to apply limit increase: {resp.text}"}
            
            res_data = resp.json()
            res = res_data.get("data", {})
            notify_event({
                "type": DataChannelEvent.LIMIT_UPDATED.value,
                "credit_limit_cents": res.get("new_limit_cents"),
                "available_credit_cents": res.get("available_credit_cents")
            })
            return {"status": "SUCCESS", "message": "Credit limit successfully updated.", "data": res}
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

async def reverse_posted_fee(transaction_id: str) -> dict:
    """Performs double-entry ledger fee reversal for the active customer's account.
    
    Args:
        transaction_id: The original late fee transaction ID to reverse.
    """
    headers = get_auth_headers()
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            reverse_url = f"{BANKING_SERVICE_URL}/credit-card/fee/reverse"
            params = {
                "transaction_id": transaction_id,
                "target_customer_id": ACTIVE_CUSTOMER_ID
            }
            resp = await client.post(reverse_url, params=params, headers=headers)
            if resp.status_code != 200:
                return {"status": "ERROR", "message": f"Failed to reverse late fee: {resp.text}"}
            
            res_data = resp.json()
            res = res_data.get("data", {})
            notify_event({
                "type": DataChannelEvent.FEE_REVERSED.value,
                "cleared_balance_cents": res.get("cleared_balance_cents"),
                "available_credit_cents": res.get("available_credit_cents")
            })
            return {"status": "SUCCESS", "message": "Late fee successfully reversed and credited.", "data": res}
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

async def get_transaction_history() -> dict:
    """Retrieves the transaction ledger history for the active customer's account.
    """
    headers = get_auth_headers()
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            tx_url = f"{BANKING_SERVICE_URL}/credit-card/transactions"
            params = {"target_customer_id": ACTIVE_CUSTOMER_ID}
            resp = await client.get(tx_url, params=params, headers=headers)
            if resp.status_code != 200:
                return {"status": "ERROR", "message": f"Failed to get transaction history: {resp.text}"}
            
            tx_list = resp.json()
            data = [{
                "transaction_id": entry.get("id"),
                "amount_cents": entry.get("amount_cents"),
                "description": entry.get("description"),
                "timestamp": entry.get("posted_at")
            } for entry in tx_list]
            return {"status": "SUCCESS", "data": data}
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

def end_consultation() -> dict:
    """Terminates the current voice consultation session. Call this when the customer confirms they are finished or want to end the call.
    """
    notify_event({"type": DataChannelEvent.SESSION_END.value})
    return {"status": "SUCCESS", "message": "Session end signal sent."}

def transfer_to_human(reason: str) -> dict:
    """Escalates the support session to a live human bank supervisor. Call this when the customer demands a human representative, disputes a fraud item that requires supervisor override, or when you are unable to resolve their request.
    
    Args:
        reason: The justification for escalating the call.
    """
    notify_event({"type": DataChannelEvent.HANDOFF_PENDING.value, "reason": reason})
    return {"status": "SUCCESS", "message": "Escalation sequence initiated."}

NAME = "credit_card_support_voice_assistant"
DESCRIPTION = "A voice assistant that helps customers freeze cards, request limit increases, and reverse late fees."

INSTRUCTION_PATH = os.path.join(os.path.dirname(__file__), "resources", "instruction.txt")
with open(INSTRUCTION_PATH, "r", encoding="utf-8") as f:
    INSTRUCTION_TEXT = f.read()

root_agent = Agent(
    name=NAME,
    description=DESCRIPTION,
    model=os.getenv("VOICE_AGENT_AUDIO_MODEL"),
    instruction=INSTRUCTION_TEXT,
    tools=[block_credit_card, apply_limit_increase, reverse_posted_fee, get_transaction_history, end_consultation, transfer_to_human],
    planner=BuiltInPlanner(
        thinking_config=ThinkingConfig(include_thoughts=False)
    )
)
