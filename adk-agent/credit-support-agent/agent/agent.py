import os
import sys
import asyncio
import google
from google.adk.agents import Agent
from google.adk.planners import BuiltInPlanner
from google.genai.types import ThinkingConfig

from agent.events import DataChannelEvent
# Resolve absolute path to banking-service and prepend to sys.path
BANKING_SERVICE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "banking-service"))
sys.path.append(BANKING_SERVICE_DIR)

from utils.database import SessionLocal
from services.credit_card import (
    freeze_card as db_freeze_card,
    apply_limit_increase as db_apply_limit_increase,
    reverse_posted_fee as db_reverse_posted_fee
)

LOCATION = "us-central1"
credentials, project_id = google.auth.default()
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project_id)
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", LOCATION)
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")

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

# Custom tools wrapped with docstrings for the LLM planner
async def block_credit_card(reason: str) -> dict:
    """Permanently blocks the active customer's primary credit card by setting its status to 'BLOCKED'.
    
    Args:
        reason: The reason for blocking the card (e.g. 'lost', 'stolen').
    """
    def sync_op():
        db = SessionLocal()
        try:
            from models.credit_card import FinancialAccount, IssuedCard
            account = db.query(FinancialAccount).filter_by(customer_id=ACTIVE_CUSTOMER_ID).first()
            if not account:
                return {"status": "ERROR", "message": f"No account found for customer '{ACTIVE_CUSTOMER_ID}'"}
            card = db.query(IssuedCard).filter_by(account_id=account.id, is_active=True).first()
            if not card:
                return {"status": "ERROR", "message": f"No active credit card found for account '{account.id}'"}
                
            res = db_freeze_card(db, card_token=card.card_token, reason=reason)
            notify_event({"type": DataChannelEvent.CARD_STATUS_LOCK.value, "status": "BLOCKED"})
            return {"status": "SUCCESS", "message": "Card successfully blocked.", "data": res}
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}
        finally:
            db.close()
    return await asyncio.to_thread(sync_op)

async def apply_limit_increase(requested_limit_cents: int) -> dict:
    """Updates the credit line limit for the active customer's account.
    
    Args:
        requested_limit_cents: The new credit limit in cents (e.g., 1200000 cents for $12,000 limit).
    """
    def sync_op():
        db = SessionLocal()
        try:
            from models.credit_card import FinancialAccount
            account = db.query(FinancialAccount).filter_by(customer_id=ACTIVE_CUSTOMER_ID).first()
            if not account:
                return {"status": "ERROR", "message": f"No account found for customer '{ACTIVE_CUSTOMER_ID}'"}
                
            res = db_apply_limit_increase(db, account_id=account.id, requested_limit_cents=requested_limit_cents)
            notify_event({
                "type": DataChannelEvent.LIMIT_UPDATED.value,
                "credit_limit_cents": res["new_limit_cents"],
                "available_credit_cents": res["available_credit_cents"]
            })
            return {"status": "SUCCESS", "message": "Credit limit successfully updated.", "data": res}
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}
        finally:
            db.close()
    return await asyncio.to_thread(sync_op)

async def reverse_posted_fee(transaction_id: str) -> dict:
    """Performs double-entry ledger fee reversal for the active customer's account.
    
    Args:
        transaction_id: The original late fee transaction ID to reverse.
    """
    def sync_op():
        db = SessionLocal()
        try:
            from models.credit_card import FinancialAccount
            account = db.query(FinancialAccount).filter_by(customer_id=ACTIVE_CUSTOMER_ID).first()
            if not account:
                return {"status": "ERROR", "message": f"No account found for customer '{ACTIVE_CUSTOMER_ID}'"}
                
            res = db_reverse_posted_fee(db, account_id=account.id, transaction_id=transaction_id, reason="CUSTOMER_VOICE_REQUEST")
            notify_event({
                "type": DataChannelEvent.FEE_REVERSED.value,
                "cleared_balance_cents": res["cleared_balance_cents"],
                "available_credit_cents": res["available_credit_cents"]
            })
            return {"status": "SUCCESS", "message": "Late fee successfully reversed and credited.", "data": res}
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}
        finally:
            db.close()
    return await asyncio.to_thread(sync_op)

async def get_transaction_history() -> dict:
    """Retrieves the transaction ledger history for the active customer's account.
    """
    def sync_op():
        db = SessionLocal()
        try:
            from models.credit_card import FinancialAccount, AccountLedger
            account = db.query(FinancialAccount).filter_by(customer_id=ACTIVE_CUSTOMER_ID).first()
            if not account:
                return {"status": "ERROR", "message": f"No account found for customer '{ACTIVE_CUSTOMER_ID}'"}
                
            entries = db.query(AccountLedger).filter_by(account_id=account.id).all()
            data = [{
                "transaction_id": entry.id,
                "amount_cents": entry.amount_cents,
                "description": entry.description,
                "timestamp": entry.posted_at.isoformat() if entry.posted_at else None
            } for entry in entries]
            return {"status": "SUCCESS", "data": data}
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}
        finally:
            db.close()
    return await asyncio.to_thread(sync_op)

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

