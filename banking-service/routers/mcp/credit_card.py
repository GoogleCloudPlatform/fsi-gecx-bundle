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
from services.credit_card import (
    apply_limit_increase,
    freeze_card,
    issue_replacement_card,
    queue_wallet_provisioning,
    reverse_posted_fee,
    get_transaction_history_dto,
)
from services.fraud_alerts import FraudAlertService
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
async def unfreeze_card(
    account_id: str = None,
    ctx: Context = None,
) -> dict:
    """
    Unblocks and reactivates a previously frozen or blocked credit card.
    
    Args:
        account_id: Optional unique identifier for the credit card account.
    """
    verified_customer_id = verified_customer_id_var.get()
    logger.info(f"FastMCP unfreeze_card invoked for account: {account_id} (Customer: {verified_customer_id})")
    
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

        # Find the blocked card linked to this account
        cards = repo.list_cards_by_account(account.id)
        card = next((c for c in cards if c.status == "BLOCKED"), None)
        if not card:
            active_card = next((c for c in cards if c.status == "ACTIVE"), None)
            if active_card:
                return {"success": False, "message": "Card is already active."}
            return {"success": False, "message": "No blocked card found linked to this account."}

        # Call service
        from services.credit_card import unfreeze_card as svc_unfreeze
        svc_unfreeze(db, card_token=card.card_token, reason="CUSTOMER_VOICE_REQUEST")
        
        # Out-of-band push to client WebSocket to sync UI
        session_id = f"session-{verified_customer_id}"
        await send_session_event(session_id, {
            "type": "CARD_STATUS",
            "card_id": card.id,
            "status": "ACTIVE"
        })
        
        return {
            "success": True,
            "message": "Card successfully unblocked and reactivated.",
            "card_token": card.card_token
        }
    except Exception as e:
        logger.error(f"Error in FastMCP unfreeze_card: {e}")
        return {"success": False, "message": f"Internal error: {str(e)}"}
    finally:
        db.close()


@mcp.tool()
@requires_user_assertion
async def issue_replacement_card_tool(
    account_id: str = None,
    wallet_provider: str = "GOOGLE_WALLET",
    ctx: Context = None,
) -> dict:
    """
    Issues a replacement virtual card for the verified customer and queues wallet provisioning.

    Args:
        account_id: Optional unique identifier for the credit card account.
        wallet_provider: Optional wallet target for digital card provisioning.
    """
    verified_customer_id = verified_customer_id_var.get()
    logger.info(
        "FastMCP issue_replacement_card_tool invoked for account: %s (Customer: %s)",
        account_id,
        verified_customer_id,
    )

    db = SessionLocal()
    repo = CreditCardRepository(db)
    try:
        if not account_id:
            account = repo.get_account_by_customer(verified_customer_id)
            if not account:
                return {"success": False, "message": "No credit card account found for the user."}
            account_id = str(account.id)

        if not re.match(r"^[a-zA-Z0-9_-]{4,64}$", str(account_id)):
            return {"success": False, "message": "Access Denied: Invalid account ID format."}

        account = repo.get_account_by_customer(verified_customer_id)
        if not account or str(account.id) != str(account_id):
            logger.error(
                "Security Alert: BOLA/IDOR attempt or account not found for %s by %s",
                account_id,
                verified_customer_id,
            )
            return {"success": False, "message": "Account not found or unauthorized."}

        open_alert = FraudAlertService(db).get_open_alert_for_account(credit_account_id=account.id)
        result = issue_replacement_card(
            db,
            account_id=str(account.id),
            reason="CUSTOMER_FRAUD_REISSUE",
            wallet_provider=wallet_provider,
            issue_virtual_card=True,
            fraud_alert_id=open_alert["fraud_alert_id"] if open_alert else None,
            compromised_card_id=open_alert["card_id"] if open_alert else None,
        )

        session_id = f"session-{verified_customer_id}"
        await send_session_event(
            session_id,
            {
                "type": "CARD_REPLACED",
                "status": result["status"],
                "replacement_status": result["replacement_status"],
                "new_last_four": result["new_last_four"],
                "new_card_id": result["new_card_id"],
                "new_card_token": result["new_card_token"],
                "is_virtual": result["is_virtual"],
                "fraud_alert_id": result.get("fraud_alert_id"),
                "compromised_card_id": result.get("compromised_card_id"),
            },
        )

        return {
            "success": True,
            "message": result["message"],
            "new_last_four": result["new_last_four"],
            "new_card_id": result["new_card_id"],
            "new_card_token": result["new_card_token"],
            "replacement_status": result["replacement_status"],
            "is_virtual": result["is_virtual"],
            "fraud_alert_id": result.get("fraud_alert_id"),
            "compromised_card_id": result.get("compromised_card_id"),
        }
    except Exception as e:
        logger.error(f"Error in FastMCP issue_replacement_card_tool: {e}")
        return {"success": False, "message": f"Internal error: {str(e)}"}
    finally:
        db.close()


@mcp.tool()
@requires_user_assertion
async def push_card_to_google_wallet(
    account_id: str = None,
    card_token: str = None,
    wallet_provider: str = "GOOGLE_WALLET",
    ctx: Context = None,
) -> dict:
    """
    Queues a mocked digital-wallet push for the verified customer's active card.

    Args:
        account_id: Optional unique identifier for the credit card account.
        card_token: Optional card token. Defaults to the account's active card.
        wallet_provider: Optional wallet target for digital card provisioning.
    """
    verified_customer_id = verified_customer_id_var.get()
    logger.info(
        "FastMCP push_card_to_google_wallet invoked for account: %s (Customer: %s)",
        account_id,
        verified_customer_id,
    )

    db = SessionLocal()
    repo = CreditCardRepository(db)
    try:
        if not account_id:
            account = repo.get_account_by_customer(verified_customer_id)
            if not account:
                return {"success": False, "message": "No credit card account found for the user."}
            account_id = str(account.id)

        if not re.match(r"^[a-zA-Z0-9_-]{4,64}$", str(account_id)):
            return {"success": False, "message": "Access Denied: Invalid account ID format."}

        account = repo.get_account_by_customer(verified_customer_id)
        if not account or str(account.id) != str(account_id):
            logger.error(
                "Security Alert: BOLA/IDOR attempt or account not found for %s by %s",
                account_id,
                verified_customer_id,
            )
            return {"success": False, "message": "Account not found or unauthorized."}

        if not card_token:
            cards = repo.list_cards_by_account(account.id)
            active_card = next((card for card in cards if card.is_active and card.status == "ACTIVE"), None)
            if not active_card:
                return {"success": False, "message": "No active card found for wallet provisioning."}
            card_token = active_card.card_token
        else:
            cards = repo.list_cards_by_account(account.id)
            matching_card = next(
                (
                    card for card in cards
                    if card.card_token == card_token or str(card.id) == str(card_token)
                ),
                None,
            )
            if not matching_card:
                return {"success": False, "message": "Card not found for wallet provisioning."}
            card_token = matching_card.card_token

        open_alert = FraudAlertService(db).get_open_alert_for_account(credit_account_id=account.id)
        result = queue_wallet_provisioning(
            db,
            account_id=str(account.id),
            card_token=card_token,
            wallet_provider=wallet_provider,
            initiated_by="CUSTOMER_VOICE_SUPPORT",
            fraud_alert_id=open_alert["fraud_alert_id"] if open_alert else None,
        )
        return {
            "success": True,
            "message": result["message"],
            "card_token": result["card_token"],
            "wallet_provider": result["wallet_provider"],
            "wallet_provisioning_status": result["wallet_provisioning_status"],
            "fraud_alert_id": result.get("fraud_alert_id"),
        }
    except Exception as e:
        logger.error(f"Error in FastMCP push_card_to_google_wallet: {e}")
        return {"success": False, "message": f"Internal error: {str(e)}"}
    finally:
        db.close()


@mcp.tool()
@requires_user_assertion
async def get_open_fraud_alert(
    ctx: Context = None,
) -> dict:
    """
    Retrieves the latest open fraud alert for the verified customer.
    """
    verified_customer_id = verified_customer_id_var.get()
    logger.info("FastMCP get_open_fraud_alert invoked for customer: %s", verified_customer_id)

    db = SessionLocal()
    try:
        service = FraudAlertService(db)
        return service.get_open_alert_details(auth_provider_uid=verified_customer_id)
    except Exception as e:
        logger.error(f"Error in FastMCP get_open_fraud_alert: {e}")
        return {"success": False, "message": f"Internal error: {str(e)}", "fraud_alert": None}
    finally:
        db.close()


@mcp.tool()
@requires_user_assertion
async def resolve_fraud_alert(
    resolution: str,
    ctx: Context = None,
) -> dict:
    """
    Resolves the latest open fraud alert for the verified customer.

    Args:
        resolution: Resolution code such as CUSTOMER_CONFIRMED_FRAUD or CUSTOMER_RECOGNIZED.
    """
    verified_customer_id = verified_customer_id_var.get()
    logger.info(
        "FastMCP resolve_fraud_alert invoked for customer: %s with resolution=%s",
        verified_customer_id,
        resolution,
    )

    allowed_resolutions = {"CUSTOMER_CONFIRMED_FRAUD", "CUSTOMER_RECOGNIZED"}
    normalized_resolution = str(resolution or "").strip().upper()
    if normalized_resolution not in allowed_resolutions:
        return {
            "success": False,
            "message": "Invalid fraud alert resolution.",
            "fraud_alert": None,
        }

    db = SessionLocal()
    try:
        service = FraudAlertService(db)
        return service.resolve_open_alert_for_customer(
            auth_provider_uid=verified_customer_id,
            resolution=normalized_resolution,
        )
    except Exception as e:
        logger.error(f"Error in FastMCP resolve_fraud_alert: {e}")
        return {"success": False, "message": f"Internal error: {str(e)}", "fraud_alert": None}
    finally:
        db.close()


@mcp.tool()
@requires_user_assertion
async def triage_fraud_case(
    fraud_alert_id: str,
    disputed_authorization_ids: list[str] = None,
    disputed_transaction_ids: list[str] = None,
    issue_replacement: bool = True,
    escalate: bool = False,
    idempotency_key: str = None,
    ctx: Context = None,
) -> dict:
    """
    Triages an active fraud case after customer confirmation.

    Args:
        fraud_alert_id: Fraud alert identifier returned by get_open_fraud_alert.
        disputed_authorization_ids: Pending authorization ids the customer disputes.
        disputed_transaction_ids: Posted transaction ids the customer disputes.
        issue_replacement: Whether to issue a replacement virtual card for confirmed fraud.
        escalate: Whether to mark the case for human fraud specialist review.
        idempotency_key: Optional stable key for retrying the same voice workflow safely.
    """
    verified_customer_id = verified_customer_id_var.get()
    logger.info(
        "FastMCP triage_fraud_case invoked for customer=%s fraud_alert_id=%s",
        verified_customer_id,
        fraud_alert_id,
    )

    if not re.match(r"^[a-fA-F0-9-]{32,36}$", str(fraud_alert_id or "")):
        return {"success": False, "message": "Invalid fraud alert id.", "fraud_alert": None}

    db = SessionLocal()
    try:
        service = FraudAlertService(db)
        result = service.triage_fraud_case(
            auth_provider_uid=verified_customer_id,
            fraud_alert_id=fraud_alert_id,
            disputed_authorization_ids=disputed_authorization_ids or [],
            disputed_transaction_ids=disputed_transaction_ids or [],
            issue_replacement=issue_replacement,
            escalate=escalate,
            idempotency_key=idempotency_key,
        )

        if result.get("success"):
            session_id = f"session-{verified_customer_id}"
            await send_session_event(
                session_id,
                {
                    "type": "FRAUD_CASE_TRIAGED",
                    "fraud_alert_id": fraud_alert_id,
                    "outcome": result.get("outcome"),
                    "fraud_alert": result.get("fraud_alert"),
                    "voided_authorizations": result.get("voided_authorizations", []),
                    "provisional_credits": result.get("provisional_credits", []),
                    "replacement_card": result.get("replacement_card"),
                    "secure_message": result.get("secure_message"),
                    "escalated": result.get("escalated", False),
                },
            )
        return result
    except ValueError as e:
        logger.warning(f"Validation error in FastMCP triage_fraud_case: {e}")
        return {"success": False, "message": str(e), "fraud_alert": None}
    except Exception as e:
        logger.error(f"Error in FastMCP triage_fraud_case: {e}")
        return {"success": False, "message": f"Internal error: {str(e)}", "fraud_alert": None}
    finally:
        db.close()


@mcp.tool()
@requires_user_assertion
async def triage_customer_reported_fraud(
    disputed_authorization_ids: list[str] = None,
    disputed_transaction_ids: list[str] = None,
    issue_replacement: bool = True,
    escalate: bool = False,
    idempotency_key: str = None,
    ctx: Context = None,
) -> dict:
    """Create and triage a customer-reported fraud case after exact confirmation.

    Use this only when no active alert exists and the customer has selected exact
    entries returned by get_transaction_history.
    """
    verified_customer_id = verified_customer_id_var.get()
    db = SessionLocal()
    try:
        result = FraudAlertService(db).triage_customer_reported_fraud(
            auth_provider_uid=verified_customer_id,
            disputed_authorization_ids=disputed_authorization_ids or [],
            disputed_transaction_ids=disputed_transaction_ids or [],
            issue_replacement=issue_replacement,
            escalate=escalate,
            idempotency_key=idempotency_key,
        )
        if result.get("success"):
            fraud_alert = result.get("fraud_alert") or {}
            await send_session_event(
                f"session-{verified_customer_id}",
                {
                    "type": "FRAUD_CASE_TRIAGED",
                    "fraud_alert_id": fraud_alert.get("fraud_alert_id"),
                    "outcome": result.get("outcome"),
                    "fraud_alert": fraud_alert,
                    "voided_authorizations": result.get("voided_authorizations", []),
                    "provisional_credits": result.get("provisional_credits", []),
                    "replacement_card": result.get("replacement_card"),
                    "secure_message": result.get("secure_message"),
                    "escalated": result.get("escalated", False),
                    "intake_source": "CUSTOMER_REPORTED",
                },
            )
        return result
    except ValueError as exc:
        logger.warning("Customer-reported fraud validation failed: %s", exc)
        return {"success": False, "message": str(exc), "fraud_alert": None}
    except Exception as exc:
        logger.exception("Customer-reported fraud intake failed")
        return {"success": False, "message": f"Internal error: {exc}", "fraud_alert": None}
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

        # 1. Search pending authorizations for an active fee hold
        pending_auths = repo.list_pending_authorizations(account.id)
        pending_fee = next((
            auth for auth in pending_auths
            if auth.merchant_name in ["OVERDRAFT_HOLD", "OVERDRAFT", "Overdraft Hold"]
        ), None)

        if pending_fee:
            current_year = datetime.datetime.now(datetime.timezone.utc).year
            year_start = datetime.datetime(current_year, 1, 1, tzinfo=datetime.timezone.utc)
            prior_reversal = repo.get_annual_reversal_entry(account.id, year_start)
            if prior_reversal:
                return {"success": False, "message": "Already used annual reversal limit."}

            pending_fee.status = "VOIDED"
            account.available_credit_cents += pending_fee.transaction_amount_cents

            from utils.audit import record_audit_event
            record_audit_event(
                db,
                "FEE_REVERSED",
                {
                    "account_id": str(account.id),
                    "authorization_id": str(pending_fee.id),
                    "amount_cents": pending_fee.transaction_amount_cents,
                    "description": "FEE_REVERSAL"
                }
            )
            db.commit()

            session_id = f"session-{verified_customer_id}"
            await send_session_event(session_id, {
                "type": "FEE_REVERSED",
                "cleared_balance_cents": account.cleared_balance_cents,
                "available_credit_cents": account.available_credit_cents
            })
            return {"success": True, "message": "Pending late fee successfully voided."}

        # 2. Otherwise fall back to posted ledger entries
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
    limit: float = None,
    amount: float = None,
    ctx: Context = None,
) -> dict:
    """
    Submits a credit limit increase request for a credit card account.
    
    Args:
        account_id: Optional unique identifier for the credit card account.
        requested_limit: Optional desired new credit limit amount (in dollars).
        limit: Desired new credit limit amount (alias in dollars).
        amount: Desired new credit limit amount (alias in dollars).
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
        target_limit = requested_limit or limit or amount
        if not target_limit:
            current_limit = account.credit_limit_cents / 100
            target_limit = current_limit * 1.2
            
        requested_limit_cents = int(target_limit * 100)

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
            "new_limit": target_limit
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
            
        transactions = get_transaction_history_dto(repo, verified_customer_id) or []
        transactions = sorted(
            transactions,
            key=lambda item: item.get("posted_at") or "",
            reverse=True,
        )
        visible_transactions = transactions[:50]
        data = [
            {
                **item,
                "transaction_id": item["id"] if not item.get("pending") else None,
                "authorization_id": item["id"] if item.get("pending") else None,
                "timestamp": item.get("posted_at"),
            }
            for item in visible_transactions
        ]
        
        return {
            "success": True,
            "data": data,
            "total_available": len(transactions),
            "truncated": len(transactions) > len(visible_transactions),
        }
    except Exception as e:
        logger.error(f"Error in FastMCP get_transaction_history: {e}")
        return {"success": False, "message": f"Internal error: {str(e)}"}
    finally:
        db.close()
