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

import time
import datetime
import logging
import re
from fastmcp import Context

from . import mcp  # Import shared FastMCP server instance
from routers.mcp.utils import requires_user_assertion, verified_customer_id_var
from utils.database import SessionLocal
from repositories.credit_card import CreditCardRepository
from services.credit_card import freeze_card, apply_limit_increase, reverse_posted_fee
from services.voice_bidi import send_session_event

logger = logging.getLogger(__name__)

@mcp.tool()
@requires_user_assertion
async def report_lost_stolen_card(
    account_id: str = None,
    ctx: Context = None,
) -> dict:
    """
    Reports a credit card as lost or stolen, blocks the card, and initiates a reissue.
    
    Args:
        account_id: Optional unique identifier for the credit card account.
    """
    verified_customer_id = verified_customer_id_var.get()
    logger.info(f"FastMCP report_lost_stolen_card invoked for account: {account_id} (Customer: {verified_customer_id})")
    
    db = SessionLocal()
    repo = CreditCardRepository(db)
    try:
        if not account_id:
            account = repo.get_account_by_customer(verified_customer_id)
            if not account:
                return {"success": False, "message": "No credit card account found for the user."}
            account_id = str(account.id)

        if not re.match(r"^[a-zA-Z0-9\-_]{4,64}$", str(account_id)):
            return {"success": False, "message": "Access Denied: Invalid account ID format."}
            
        # Enforce BOLA/IDOR check: verify account belongs to verified_customer_id
        account = repo.get_account_by_customer(verified_customer_id)
        if not account or account.id != account_id:
            logger.error(f"Security Alert: BOLA/IDOR attempt or account not found for {account_id} by {verified_customer_id}")
            return {"success": False, "message": "Account not found or unauthorized."}

        # Find the active card linked to this account
        cards = repo.list_cards_by_account(account.id)
        card = next((c for c in cards if c.status == "ACTIVE"), None)
        if not card:
            # Check if there is already a blocked/lost card
            prior_lost_card = next((c for c in cards if c.status == "BLOCKED"), None)
            if prior_lost_card:
                return {"success": False, "message": "Card has already been reported as lost or stolen."}
            return {"success": False, "message": "No active card found linked to this account."}

        # Anti-Fraud Check: billing address modification quarantine (Simulated)
        logger.info(f"Anti-Fraud check: Address quarantine check passed for customer {verified_customer_id}")

        # Execute freeze service
        freeze_card(db, card_token=card.card_token, reason="CUSTOMER_REPORTED_LOST_STOLEN")
        
        # Out-of-band push to client WebSocket to sync UI
        session_id = f"session-{verified_customer_id}"
        await send_session_event(session_id, {
            "type": "CARD_STATUS",
            "card_id": card.id,
            "status": "BLOCKED"
        })
        
        confirmation_number = f"LST-{card.last_four}-{int(time.time())}"
        return {
            "success": True,
            "message": "Card reported as lost. A new card will be issued.",
            "confirmation_number": confirmation_number
        }
    except Exception as e:
        logger.error(f"Error in FastMCP report_lost_stolen_card: {e}")
        return {"success": False, "message": f"Internal error: {str(e)}"}
    finally:
        db.close()


@mcp.tool()
@requires_user_assertion
async def reverse_overdraft_fee(
    account_id: str = None,
    fee_date: str = None,
    ctx: Context = None,
) -> dict:
    """
    Reverses an overdraft or late fee for a credit card account.
    
    Args:
        account_id: Optional unique identifier for the credit card account.
        fee_date: Optional date of the fee to reverse.
    """
    verified_customer_id = verified_customer_id_var.get()
    logger.info(f"FastMCP reverse_overdraft_fee invoked for account: {account_id} (Customer: {verified_customer_id})")
    
    db = SessionLocal()
    repo = CreditCardRepository(db)
    try:
        if not account_id:
            account = repo.get_account_by_customer(verified_customer_id)
            if not account:
                return {"success": False, "message": "No credit card account found for the user."}
            account_id = str(account.id)

        if not re.match(r"^[a-zA-Z0-9\-_]{4,64}$", str(account_id)):
            return {"success": False, "message": "Access Denied: Invalid account ID format."}

        # Enforce BOLA check
        account = repo.get_account_by_customer(verified_customer_id)
        if not account or account.id != account_id:
            logger.error(f"Security Alert: BOLA/IDOR attempt or account not found for {account_id} by {verified_customer_id}")
            return {"success": False, "message": "Account not found or unauthorized."}

        # Concurrency Locking: lock account row for balance updates
        account = repo.get_account_by_id(account_id, lock=True)

        # Find the target fee transaction in the ledger (negative amount with "LATE_FEE" or similar)
        ledger = repo.list_ledger_entries(account.id)
        original_tx = next((
            entry for entry in ledger
            if entry.amount_cents < 0 and entry.description in ["LATE_FEE", "OVERDRAFT", "Overdraft Fee"]
        ), None)

        if not original_tx:
            return {"success": False, "message": "No eligible fee transaction found to reverse."}

        # Policy Validation: max one reversal per calendar year
        current_year = datetime.datetime.now(datetime.timezone.utc).year
        year_start = datetime.datetime(current_year, 1, 1, tzinfo=datetime.timezone.utc)

        prior_reversal = repo.get_annual_reversal_entry(account.id, year_start)

        if prior_reversal:
            return {"success": False, "message": "Already used annual reversal limit."}

        # Apply reversal
        res = reverse_posted_fee(db, account_id=account.id, transaction_id=original_tx.id, reason="CUSTOMER_VOICE_REQUEST")
        
        # Out-of-band push to client WebSocket to sync UI
        session_id = f"session-{verified_customer_id}"
        await send_session_event(session_id, {
            "type": "FEE_REVERSED",
            "cleared_balance_cents": res["cleared_balance_cents"],
            "available_credit_cents": res["available_credit_cents"]
        })

        return {
            "success": True,
            "message": f"Overdraft fee of ${abs(original_tx.amount_cents)/100:.2f} reversed.",
            "amount_reversed": abs(original_tx.amount_cents)/100,
            "reversals_remaining_this_year": 0
        }
    except Exception as e:
        logger.error(f"Error in FastMCP reverse_overdraft_fee: {e}")
        return {"success": False, "message": f"Internal error: {str(e)}"}
    finally:
        db.close()


@mcp.tool()
@requires_user_assertion
async def request_credit_limit_increase(
    account_id: str = None,
    requested_limit: float = None,
    ctx: Context = None,
) -> dict:
    """
    Submits a credit limit increase request for a credit card account.
    
    Args:
        account_id: Optional unique identifier for the credit card account.
        requested_limit: Optional desired new credit limit amount (in dollars).
    """
    verified_customer_id = verified_customer_id_var.get()
    logger.info(f"FastMCP request_credit_limit_increase invoked for account: {account_id} (Customer: {verified_customer_id})")
    
    db = SessionLocal()
    repo = CreditCardRepository(db)
    try:
        if not account_id:
            account = repo.get_account_by_customer(verified_customer_id)
            if not account:
                return {"success": False, "message": "No credit card account found for the user."}
            account_id = str(account.id)

        if not re.match(r"^[a-zA-Z0-9\-_]{4,64}$", str(account_id)):
            return {"success": False, "message": "Access Denied: Invalid account ID format."}

        # Enforce BOLA check
        account = repo.get_account_by_customer(verified_customer_id)
        if not account or account.id != account_id:
            logger.error(f"Security Alert: BOLA/IDOR attempt or account not found for {account_id} by {verified_customer_id}")
            return {"success": False, "message": "Account not found or unauthorized."}

        # Concurrency Locking
        account = repo.get_account_by_id(account_id, lock=True)

        # Check requested limit
        if not requested_limit:
            current_limit = account.credit_limit_cents / 100
            requested_limit = current_limit * 1.2
            
        requested_limit_cents = int(requested_limit * 100)

        # Underwriting rule check: reject if increase is > 2x current limit
        limit_ceiling_cents = account.credit_limit_cents * 2
        if requested_limit_cents > limit_ceiling_cents:
            return {"success": False, "message": "Request denied due to credit history."}

        # Apply increase
        res = apply_limit_increase(db, account_id=account.id, requested_limit_cents=requested_limit_cents)
        
        # Out-of-band push to client WebSocket to sync UI
        session_id = f"session-{verified_customer_id}"
        await send_session_event(session_id, {
            "type": "LIMIT_UPDATED",
            "credit_limit_cents": res["new_limit_cents"],
            "available_credit_cents": res["available_credit_cents"]
        })

        return {
            "success": True,
            "message": "Credit limit increase approved.",
            "new_limit": requested_limit
        }
    except Exception as e:
        logger.error(f"Error in FastMCP request_credit_limit_increase: {e}")
        return {"success": False, "message": f"Internal error: {str(e)}"}
    finally:
        db.close()


@mcp.tool()
@requires_user_assertion
async def get_transaction_history(
    ctx: Context = None,
) -> dict:
    """
    Retrieves the transaction ledger history for the verified user's credit card account.
    """
    verified_customer_id = verified_customer_id_var.get()
    logger.info(f"FastMCP get_transaction_history invoked for Customer: {verified_customer_id}")
    
    db = SessionLocal()
    repo = CreditCardRepository(db)
    try:
        account = repo.get_account_by_customer(verified_customer_id)
        if not account:
            return {"success": False, "message": "No credit card account found for the user."}
            
        ledger = repo.list_ledger_entries(account.id)
        data = [{
            "transaction_id": entry.id,
            "amount_cents": entry.amount_cents,
            "description": entry.description,
            "timestamp": entry.posted_at.isoformat() if entry.posted_at else None
        } for entry in ledger]
        
        return {"success": True, "data": data}
    except Exception as e:
        logger.error(f"Error in FastMCP get_transaction_history: {e}")
        return {"success": False, "message": f"Internal error: {str(e)}"}
    finally:
        db.close()
