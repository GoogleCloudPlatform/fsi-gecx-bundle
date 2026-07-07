from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import random
import uuid

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.authentication import ValidatedToken
from models.credit_card import TransactionAuthorization
from repositories.accounts import AccountsRepository
from repositories.credit_card import CreditCardRepository
from services.accounts import AccountsService
from services.cdc_monitoring import CdcMonitoringService
from services.seeding_service import (
    is_demo_script_user_email,
    provision_user_suite,
    reset_user_suite,
)
from services.fraud_alerts import FraudAlertService
from utils.audit import record_audit_event
from utils.database import enable_session_rbac_override
from utils.internal_auth import get_internal_switch_token
from utils.internal_execution import InternalServiceContext, apply_internal_db_access

logger = logging.getLogger(__name__)

DATA_GENERATOR_URL = os.getenv("DATA_GENERATOR_URL", "http://localhost:8001")
SURGE_DISPATCH_CONNECT_TIMEOUT_SECONDS = float(os.getenv("SURGE_DISPATCH_CONNECT_TIMEOUT_SECONDS", "5"))
SURGE_DISPATCH_READ_TIMEOUT_SECONDS = float(os.getenv("SURGE_DISPATCH_READ_TIMEOUT_SECONDS", "8"))


class SimulationService:
    def __init__(self, db: Session):
        self.db = db
        self.accounts_repo = AccountsRepository(db)
        self.credit_repo = CreditCardRepository(db)

    def _enable_simulation_db_access(self) -> None:
        enable_session_rbac_override(self.db)

    def _resolve_demo_user(self, token: ValidatedToken):
        self._enable_simulation_db_access()
        user = self.accounts_repo.get_user_by_auth_provider_uid(token.user_id)
        if not user and token.email:
            user = self.accounts_repo.get_user_by_email(token.email)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demo profile not found.")
        return user

    @staticmethod
    def _build_service_headers(target_url: str) -> dict[str, str]:
        headers = {"X-Card-Network-Token": get_internal_switch_token()}

        if target_url and "localhost" not in target_url and "127.0.0.1" not in target_url:
            try:
                import google.auth
                import google.auth.transport.requests
                from google.oauth2 import id_token

                auth_req = google.auth.transport.requests.Request()
                oidc_token = id_token.fetch_id_token(auth_req, target_url)
                if not oidc_token:
                    raise RuntimeError("OIDC token fetch returned an empty token.")
                headers["Authorization"] = f"Bearer {oidc_token}"
            except Exception as auth_err:
                logger.exception("Failed to fetch OIDC token for simulation dependency target=%s", target_url)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Could not authenticate to simulation dependency.",
                ) from auth_err

        return headers

    def provision_my_demo(self, token: ValidatedToken) -> dict:
        if not token.email or not token.user_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Authenticated user context is incomplete.")

        try:
            summary = provision_user_suite(self.db, token.email, token.user_id)
            return {"status": "SUCCESS", "message": "Demo profile provisioned successfully.", "summary": summary}
        except ValueError as val_err:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(val_err)) from val_err
        except Exception as exc:
            logger.error("Failed to provision demo profile for email=%s: %s", token.email, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to provision demo profile.",
            ) from exc

    def reset_my_demo(self, token: ValidatedToken) -> dict:
        if not token.user_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Authenticated user ID not found in token claims.")

        try:
            user = self._resolve_demo_user(token)
            reset_user_suite(self.db, user.id)
            return {"status": "SUCCESS", "message": "Demo profile reset successfully."}
        except HTTPException as exc:
            if exc.status_code == status.HTTP_404_NOT_FOUND and exc.detail == "Demo profile not found.":
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No seeded demo profile found for the authenticated presenter.",
                ) from exc
            raise
        except Exception as exc:
            logger.error("Failed to reset demo profile for user_id=%s: %s", user.id, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to reset demo profile.",
            ) from exc

    def list_active_cards_for_simulation(self) -> dict:
        self._enable_simulation_db_access()
        cards = self.credit_repo.list_active_cards_for_simulation()

        results = []
        for card, acc, user in cards:
            name_lower = card.cardholder_name.lower() if card.cardholder_name else ""
            email_lower = (user.email or "").lower() if user and user.email else ""
            is_demo_script_account = is_demo_script_user_email(email_lower)
            is_presenter_account = email_lower.endswith("@google.com") or email_lower.endswith("@gcp.solutions") or email_lower.endswith("@altostrat.com")
            is_vip_demo_account = email_lower.endswith("@nova.horizon.test")
            generator_eligible = not is_demo_script_account
            if "erik" in name_lower or acc.credit_limit_cents > 2_000_000:
                persona = "HNW"
                mccs, a_min, a_max = ["4511", "7011", "5812"], 50_000, 400_000
            elif "servedio" in name_lower or "marcus" in name_lower or acc.credit_limit_cents >= 1_000_000:
                persona = "PRIME"
                mccs, a_min, a_max = ["5411", "5541", "5311", "4121"], 1_500, 15_000
            else:
                persona = "YPRO"
                mccs, a_min, a_max = ["5814", "4899", "5812"], 400, 3_500

            results.append(
                {
                    "card_token": card.card_token,
                    "cardholder_name": card.cardholder_name,
                    "credit_account_id": str(acc.id),
                    "customer_id": str(acc.customer_id),
                    "persona": persona,
                    "mccs": mccs,
                    "amount_min": a_min,
                    "amount_max": a_max,
                    "credit_limit_cents": acc.credit_limit_cents,
                    "available_credit_cents": acc.available_credit_cents,
                    "generator_eligible": generator_eligible,
                    "is_demo_script_account": is_demo_script_account,
                    "is_presenter_account": is_presenter_account,
                    "is_vip_demo_account": is_vip_demo_account,
                }
            )

        return {"active_cards": results, "count": len(results)}

    async def dispatch_spend_surge(self) -> dict:
        active_cards = self.list_active_cards_for_simulation()
        card_payloads = active_cards.get("active_cards", [])
        if not card_payloads:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No active cards are available for spend surge simulation.")

        target_url = f"{DATA_GENERATOR_URL}/simulate-surge"
        logger.info("Forwarding surge request to data-generator at %s with %s active cards.", target_url, len(card_payloads))

        headers = self._build_service_headers(DATA_GENERATOR_URL)
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    target_url,
                    json={"active_cards": card_payloads},
                    headers=headers,
                    timeout=httpx.Timeout(
                        connect=SURGE_DISPATCH_CONNECT_TIMEOUT_SECONDS,
                        read=SURGE_DISPATCH_READ_TIMEOUT_SECONDS,
                        write=10.0,
                        pool=5.0,
                    ),
                )
                if response.status_code != 200:
                    logger.warning(
                        "Data generator surge request failed. status=%s body=%s",
                        response.status_code,
                        response.text,
                    )
                    raise HTTPException(
                        status_code=response.status_code,
                        detail="Data generator surge request failed.",
                    )
                return response.json()
        except (httpx.ReadTimeout, httpx.RemoteProtocolError, httpx.ReadError) as exc:
            logger.warning(
                "Surge dispatch response from data-generator was interrupted after submission; treating request as accepted. target=%s error=%s",
                target_url,
                exc,
            )
            return {
                "status": "ACCEPTED",
                "message": "Spend surge dispatch was accepted. Downstream execution is still in progress; monitor the live transaction stream for results.",
                "active_cards_count": len(card_payloads),
            }
        except httpx.RequestError as exc:
            logger.error("Network error trying to connect to data generator at %s: %s", target_url, exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not connect to synthetic data generator.",
            ) from exc

    def inject_targeted_fraud(self, token: ValidatedToken) -> dict:
        user = self._resolve_demo_user(token)
        self._enable_simulation_db_access()
        target_card = self.credit_repo.get_active_card_for_customer(str(user.id))
        if not target_card:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active credit card found for user.")

        card, cred_acc = target_card
        now = datetime.datetime.now(datetime.timezone.utc)
        swipes = [
            ("GAME*TEST TOKEN ONLINE", 499, "5814", "USA", 0),
            ("APPLE.COM*ONLINE", 149900, "4899", "USA", 0),
            ("BEST BUY*MKTPLACE", 215000, "5311", "USA", 0),
            ("LUXURY BOUTIQUE RIVIERA MAYA [MEX]", 320000, "5311", "MEX", 30),
        ]

        injected_auths = []
        for idx, (desc, amt, mcc, country, risk) in enumerate(swipes):
            auth = TransactionAuthorization(
                id=uuid.uuid4(),
                card_id=card.id,
                account_id=cred_acc.id,
                transaction_amount_cents=amt,
                billing_amount_cents=amt,
                status="PENDING",
                auth_code=f"FRD{random.randint(100, 999)}",
                retrieval_reference_number=f"REF{999000+idx:09d}",
                card_network="VISA",
                merchant_category_code=mcc,
                merchant_name=desc,
                created_at=now + datetime.timedelta(seconds=idx),
                expires_at=now + datetime.timedelta(days=7),
            )
            self.db.add(auth)
            injected_auths.append(auth)
            record_audit_event(
                self.db,
                "CREDIT_TRANSACTION_AUTHORIZED",
                {
                    "account_id": str(cred_acc.id),
                    "authorization_id": str(auth.id),
                    "amount_cents": amt,
                    "merchant_name": desc,
                    "is_fraud_simulation": True,
                    "risk_score": risk,
                },
            )

        fraud_alert = FraudAlertService(self.db).create_alert_from_simulation(
            auth_token=token,
            customer=user,
            card=card,
            credit_account=cred_acc,
            suspicious_authorizations=injected_auths,
        )
        self.db.commit()
        logger.info("Injected 4 targeted fraud anomaly swipes for user=%s (%s).", user.id, token.email)
        return {
            "status": "ANOMALY_INJECTED",
            "user_id": str(user.id),
            "card_token": card.card_token,
            "injected_swipes_count": len(injected_auths),
            "total_fraud_cents": sum(amt for _, amt, _, _, _ in swipes),
            "fraud_alert_id": fraud_alert["fraud_alert_id"],
            "secure_message_thread_id": fraud_alert["thread_id"],
            "message": "Fraud surge successfully injected into cards.transaction_authorizations.",
        }

    def inject_late_fee(self, token: ValidatedToken) -> dict:
        from services.card_network import process_authorization

        user = self._resolve_demo_user(token)
        target_card = self.credit_repo.get_active_card_for_customer(str(user.id))
        if not target_card:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active credit card found for user.")

        card, cred_acc = target_card
        now = datetime.datetime.now(datetime.timezone.utc)
        rrn = f"FEE_{str(user.id)[:5]}_{random.randint(10, 99)}"

        auth_res = process_authorization(
            self.db,
            {
                "card_token": card.card_token,
                "amount_cents": 3500,
                "retrieval_reference_number": rrn,
                "merchant_category_code": "FEE",
                "merchant_name": "LATE_FEE",
                "card_network": "VISA",
                "created_at": now,
            },
        )
        if auth_res.get("action_code") == "00":
            record_audit_event(
                self.db,
                "CREDIT_TRANSACTION_AUTHORIZED",
                {
                    "account_id": str(cred_acc.id),
                    "amount_cents": 3500,
                    "merchant_name": "LATE_FEE",
                    "is_late_fee_simulation": True,
                },
            )

        logger.info("Injected $35.00 Late Fee hold for user=%s (%s).", user.id, token.email)
        return {
            "status": "LATE_FEE_INJECTED",
            "user_id": str(user.id),
            "card_token": card.card_token,
            "amount_cents": 3500,
            "retrieval_reference_number": rrn,
            "message": "Late fee ($35.00) hold successfully authorized on ledger.",
        }

    def get_global_stream(self) -> dict:
        service = CdcMonitoringService(self.db)
        return {
            **service.get_operational_stream(limit=20),
            "stream_metrics": service.get_operational_stream_metrics(),
            "cdc_metrics": service.get_cached_datastream_metrics(),
        }

    def get_cdc_status(self) -> dict:
        return CdcMonitoringService(self.db).get_cdc_status()

    def execute_internal_auto_paydown(
        self,
        context: InternalServiceContext,
        customer_id: str,
        credit_account_id: str,
        target_utilization: float = 0.35,
        trigger_utilization: float = 0.65,
    ) -> dict:
        if trigger_utilization <= 0 or target_utilization < 0 or target_utilization >= trigger_utilization:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid utilization thresholds.")

        apply_internal_db_access(self.db, context, "simulation:autopaydown")

        user = self.accounts_repo.get_user_by_id(customer_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")

        credit_acc = self.accounts_repo.get_credit_account_for_user(user.id, credit_account_id)
        if not credit_acc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target credit account not found.")

        if credit_acc.credit_limit_cents <= 0:
            return {"status": "SKIPPED", "message": "Credit account has no usable limit.", "payments": []}

        utilization = credit_acc.cleared_balance_cents / credit_acc.credit_limit_cents
        if utilization < trigger_utilization or credit_acc.cleared_balance_cents <= 0:
            return {
                "status": "SKIPPED",
                "message": "Credit account utilization below auto-paydown threshold.",
                "payments": [],
                "utilization": round(utilization, 4),
            }

        target_balance_cents = int(credit_acc.credit_limit_cents * target_utilization)
        amount_needed_cents = max(0, credit_acc.cleared_balance_cents - target_balance_cents)
        if amount_needed_cents <= 0:
            return {"status": "SKIPPED", "message": "No paydown required.", "payments": []}

        funding_accounts = self.accounts_repo.list_funding_accounts_for_user(user.id)
        checking_accounts = [acc for acc in funding_accounts if acc.account_type == "CHECKING"]
        savings_accounts = [acc for acc in funding_accounts if acc.account_type == "SAVINGS"]
        ordered_funding_accounts = checking_accounts + savings_accounts

        payments = []
        remaining_cents = amount_needed_cents
        accounts_service = AccountsService(self.db)

        for deposit_acc in ordered_funding_accounts:
            if remaining_cents <= 0:
                break

            available_funds = max(0, deposit_acc.cleared_balance_cents)
            if available_funds <= 0:
                continue

            payment_amount = min(remaining_cents, available_funds)
            payment_result = accounts_service.execute_bill_payment_for_user(
                user=user,
                source_account_id=str(deposit_acc.id),
                credit_account_id=credit_account_id,
                amount_cents=payment_amount,
                internal_context=context,
            )
            payments.append(
                {
                    "source_account_id": str(deposit_acc.id),
                    "source_account_type": deposit_acc.account_type,
                    "amount_cents": payment_amount,
                    "result": payment_result,
                }
            )
            remaining_cents -= payment_amount

        self.db.refresh(credit_acc)
        final_utilization = credit_acc.cleared_balance_cents / credit_acc.credit_limit_cents
        total_paid_cents = sum(payment["amount_cents"] for payment in payments)

        return {
            "status": "SUCCESS" if total_paid_cents > 0 else "SKIPPED",
            "message": "Auto-paydown processed." if total_paid_cents > 0 else "No deposit funds available for auto-paydown.",
            "payments": payments,
            "target_amount_cents": amount_needed_cents,
            "paid_amount_cents": total_paid_cents,
            "remaining_amount_cents": max(0, remaining_cents),
            "final_credit_cleared_balance_cents": credit_acc.cleared_balance_cents,
            "final_credit_available_credit_cents": credit_acc.available_credit_cents,
            "final_utilization": round(final_utilization, 4),
        }

    async def stream_payload(self, token: ValidatedToken):
        del token

        cdc_service = CdcMonitoringService(self.db)
        from utils.redis_client import get_redis_client

        redis_client = get_redis_client()
        pubsub = redis_client.pubsub() if redis_client else None
        last_heartbeat = 0.0

        def build_payload(kind: str) -> str:
            return json.dumps(
                {
                    "status": "SUCCESS",
                    "event_kind": kind,
                    "operational_stream": cdc_service.get_operational_stream(limit=20)["stream"],
                    "stream_metrics": cdc_service.get_operational_stream_metrics(),
                    "cdc_metrics": cdc_service.get_cached_datastream_metrics(),
                    "cdc_status": cdc_service.get_cdc_status(),
                }
            )

        if pubsub:
            pubsub.subscribe("channel:transactions:live")

        try:
            yield f"data: {build_payload('snapshot')}\n\n"
            last_heartbeat = asyncio.get_running_loop().time()

            while True:
                try:
                    message = None
                    if pubsub:
                        message = await asyncio.to_thread(
                            pubsub.get_message,
                            ignore_subscribe_messages=True,
                            timeout=5.0,
                        )

                    now = asyncio.get_running_loop().time()
                    if message and message.get("data"):
                        yield f"data: {build_payload('event')}\n\n"
                        last_heartbeat = now
                        continue

                    if now - last_heartbeat >= 10:
                        yield f"data: {build_payload('heartbeat')}\n\n"
                        last_heartbeat = now

                    if not pubsub:
                        await asyncio.sleep(1)
                except Exception as exc:
                    logger.error("Error generating SSE stream: %s", exc)
                    await asyncio.sleep(2)
        finally:
            if pubsub:
                try:
                    pubsub.unsubscribe("channel:transactions:live")
                    pubsub.close()
                except Exception:
                    pass
