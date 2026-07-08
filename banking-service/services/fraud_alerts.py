import hashlib
import uuid
from typing import Iterable

from models.authentication import ValidatedToken
from models.credit_card import CreditAccount, IssuedCard, TransactionAuthorization
from models.secure_messaging import SecureMessageCreateRequest, SENDER_TYPE_BANK
from repositories.fraud import FraudAlertRepository
from services.knowledge_catalog import KnowledgeCatalogService
from services.messaging import MessagingService
from utils.audit import record_audit_event


class FraudAlertService:
    def __init__(self, db):
        self.db = db
        self.repo = FraudAlertRepository(db)
        self.messaging = MessagingService(db)

    def create_alert_from_simulation(
        self,
        *,
        auth_token: ValidatedToken,
        customer,
        card: IssuedCard,
        credit_account: CreditAccount,
        suspicious_authorizations: Iterable[TransactionAuthorization],
    ) -> dict:
        suspicious_authorizations = list(suspicious_authorizations)
        thread_id = str(uuid.uuid4())
        suspicious_transactions = [
            {
                "authorization_id": str(auth.id),
                "merchant_name": auth.merchant_name,
                "amount_cents": auth.transaction_amount_cents,
                "merchant_category_code": auth.merchant_category_code,
                "card_network": auth.card_network,
                "created_at": auth.created_at.isoformat() if auth.created_at else None,
            }
            for auth in suspicious_authorizations
        ]

        alert = self.repo.create_alert(
            customer_id=customer.id,
            auth_provider_uid=customer.auth_provider_uid or auth_token.user_id,
            credit_account_id=credit_account.id,
            card_id=card.id,
            card_last_four=card.last_four,
            message_thread_id=thread_id,
            suspicious_authorization_ids=[str(auth.id) for auth in suspicious_authorizations],
            suspicious_transactions=suspicious_transactions,
        )
        record_audit_event(
            self.db,
            "FRAUD_ALERT_CREATED",
            {
                "fraud_alert_id": str(alert.id),
                "correlation_id": str(alert.id),
                "customer_id": str(customer.id),
                "credit_account_id": str(credit_account.id),
                "card_last_four": card.last_four,
                "authorization_ids": [str(auth.id) for auth in suspicious_authorizations],
                "source": alert.source,
            },
        )

        message_request = SecureMessageCreateRequest(
            category="Fraud Alert",
            message=self._build_customer_message(card.last_four, suspicious_transactions),
            thread_id=thread_id,
            user_id=customer.auth_provider_uid or auth_token.user_id,
            sender=SENDER_TYPE_BANK,
        )
        message = self.messaging.create_message(message_request, auth_token)

        record_audit_event(
            self.db,
            "FRAUD_ALERT_CUSTOMER_NOTIFIED",
            {
                "fraud_alert_id": str(alert.id),
                "correlation_id": str(alert.id),
                "customer_id": str(customer.id),
                "message_id": message.message_id,
                "thread_id": message.thread_id,
                "channel": "SECURE_MESSAGE_AND_PUSH",
            },
        )

        return {
            "fraud_alert_id": str(alert.id),
            "thread_id": message.thread_id,
            "message_id": message.message_id,
        }

    def get_active_voice_context(
        self,
        *,
        customer_id=None,
        auth_provider_uid: str | None = None,
    ) -> dict:
        alert = self.repo.get_latest_open_alert_for_customer(
            customer_id=customer_id,
            auth_provider_uid=auth_provider_uid,
        )
        if not alert:
            return {
                "entry_reason": "general_support",
                "has_active_fraud_alert": False,
                "fraud_alert": None,
                "support_guidance": {"source": "not_applicable", "topic_ids": [], "topics": [], "agent_guidance_summary": ""},
            }

        suspicious_transactions = alert.suspicious_transactions or []
        guidance = KnowledgeCatalogService().get_guidance_bundle_for_voice_fraud()
        return {
            "entry_reason": "fraud_alert",
            "has_active_fraud_alert": True,
            "fraud_alert": {
                "fraud_alert_id": str(alert.id),
                "status": alert.status,
                "source": alert.source,
                "card_last_four": alert.card_last_four,
                "message_thread_id": alert.message_thread_id,
                "suspicious_transactions": suspicious_transactions,
                "created_at": alert.created_at.isoformat() if alert.created_at else None,
                "summary": self._build_voice_context_summary(alert.card_last_four, suspicious_transactions),
            },
            "support_guidance": guidance,
        }

    def get_open_alert_details(
        self,
        *,
        customer_id=None,
        auth_provider_uid: str | None = None,
    ) -> dict:
        context = self.get_active_voice_context(
            customer_id=customer_id,
            auth_provider_uid=auth_provider_uid,
        )
        if not context["has_active_fraud_alert"]:
            return {
                "success": False,
                "message": "No open fraud alert found for the customer.",
                "fraud_alert": None,
            }
        return {
            "success": True,
            "message": "Open fraud alert retrieved successfully.",
            "fraud_alert": context["fraud_alert"],
        }

    def get_open_alert_for_account(self, *, credit_account_id) -> dict | None:
        alert = self.repo.get_open_alert_for_account(credit_account_id=credit_account_id)
        if not alert:
            return None
        return {
            "fraud_alert_id": str(alert.id),
            "status": alert.status,
            "source": alert.source,
            "card_id": str(alert.card_id),
            "card_last_four": alert.card_last_four,
            "message_thread_id": alert.message_thread_id,
        }

    def resolve_open_alert_for_customer(
        self,
        *,
        auth_provider_uid: str,
        resolution: str,
    ) -> dict:
        alert = self.repo.get_latest_open_alert_for_customer(auth_provider_uid=auth_provider_uid)
        if not alert:
            return {
                "success": False,
                "message": "No open fraud alert found for the customer.",
                "fraud_alert": None,
            }

        resolved_status = f"RESOLVED_{resolution.upper()}"
        alert = self.repo.resolve_alert(
            fraud_alert_id=alert.id,
            resolved_status=resolved_status,
        )
        record_audit_event(
            self.db,
            "FRAUD_ALERT_RESOLVED",
            {
                "fraud_alert_id": str(alert.id),
                "correlation_id": str(alert.id),
                "customer_id": str(alert.customer_id),
                "credit_account_id": str(alert.credit_account_id),
                "resolution": resolution.upper(),
                "status": alert.status,
            },
        )
        self.db.commit()
        return {
            "success": True,
            "message": "Fraud alert resolved successfully.",
            "fraud_alert": {
                "fraud_alert_id": str(alert.id),
                "status": alert.status,
                "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
                "resolution": resolution.upper(),
                "card_last_four": alert.card_last_four,
            },
        }

    def triage_fraud_case(
        self,
        *,
        auth_provider_uid: str,
        fraud_alert_id: str,
        disputed_authorization_ids: list[str] | None = None,
        disputed_transaction_ids: list[str] | None = None,
        issue_replacement: bool = True,
        escalate: bool = False,
        idempotency_key: str | None = None,
    ) -> dict:
        """
        Deterministic fraud triage workflow for Gemini Live and MCP callers.

        The method deliberately centralizes business sequencing so the live agent
        can confirm customer intent once and invoke a single workflow operation.
        """
        disputed_authorization_ids = disputed_authorization_ids or []
        disputed_transaction_ids = disputed_transaction_ids or []
        alert = self.repo.get_alert_for_customer(
            fraud_alert_id=fraud_alert_id,
            auth_provider_uid=auth_provider_uid,
        )
        if not alert:
            return {
                "success": False,
                "message": "No fraud alert found for the customer.",
                "fraud_alert": None,
            }

        workflow_key = idempotency_key or self._build_triage_idempotency_key(
            disputed_authorization_ids=disputed_authorization_ids,
            disputed_transaction_ids=disputed_transaction_ids,
            issue_replacement=issue_replacement,
            escalate=escalate,
        )
        workflow_action = self.repo.get_case_action_by_idempotency_key(
            fraud_alert_id=alert.id,
            idempotency_key=workflow_key,
        )
        if workflow_action and workflow_action.status == "SUCCEEDED":
            result = dict(workflow_action.result_payload or {})
            result["idempotent_replay"] = True
            return result
        if not workflow_action:
            workflow_action = self.repo.create_case_action(
                fraud_alert_id=alert.id,
                action_type="FRAUD_CASE_TRIAGED",
                status="PENDING",
                idempotency_key=workflow_key,
                request_payload={
                    "disputed_authorization_ids": disputed_authorization_ids,
                    "disputed_transaction_ids": disputed_transaction_ids,
                    "issue_replacement": issue_replacement,
                    "escalate": escalate,
                },
            )

        allowed_authorization_ids = set(str(auth_id) for auth_id in (alert.suspicious_authorization_ids or []))
        if allowed_authorization_ids:
            unexpected = sorted(set(disputed_authorization_ids) - allowed_authorization_ids)
            if unexpected:
                raise ValueError(f"Authorization ids are not part of this fraud alert: {', '.join(unexpected)}")

        has_disputes = bool(disputed_authorization_ids or disputed_transaction_ids)
        if not has_disputes:
            resolved = self.repo.resolve_alert(
                fraud_alert_id=alert.id,
                resolved_status="RESOLVED_CUSTOMER_RECOGNIZED",
            )
            message = self._send_triage_secure_message(
                auth_provider_uid=auth_provider_uid,
                alert=resolved,
                message_body=self._build_recognized_triage_message(resolved),
            )
            self.repo.mark_triaged(
                fraud_alert_id=resolved.id,
                remediation_status="CUSTOMER_RECOGNIZED",
                triage_summary="Customer recognized all suspicious transactions.",
                selected_disputed_authorization_ids=[],
                selected_disputed_transaction_ids=[],
                provisional_credit_cents=0,
                triage_message_thread_id=message.thread_id,
                triage_message_id=message.message_id,
            )
            record_audit_event(
                self.db,
                "FRAUD_ALERT_RESOLVED",
                {
                    "fraud_alert_id": str(resolved.id),
                    "correlation_id": str(resolved.id),
                    "customer_id": str(resolved.customer_id),
                    "credit_account_id": str(resolved.credit_account_id),
                    "card_id": str(resolved.card_id),
                    "resolution": "CUSTOMER_RECOGNIZED",
                    "status": resolved.status,
                },
            )
            record_audit_event(
                self.db,
                "FRAUD_CASE_TRIAGED",
                {
                    "fraud_alert_id": str(resolved.id),
                    "correlation_id": str(resolved.id),
                    "customer_id": str(resolved.customer_id),
                    "credit_account_id": str(resolved.credit_account_id),
                    "card_id": str(resolved.card_id),
                    "outcome": "CUSTOMER_RECOGNIZED",
                    "disputed_authorization_ids": [],
                    "disputed_transaction_ids": [],
                },
            )
            record_audit_event(
                self.db,
                "FRAUD_TRIAGE_MESSAGE_SENT",
                {
                    "fraud_alert_id": str(resolved.id),
                    "correlation_id": str(resolved.id),
                    "customer_id": str(resolved.customer_id),
                    "thread_id": message.thread_id,
                    "message_id": message.message_id,
                },
            )
            result = {
                "success": True,
                "message": "Fraud alert marked as recognized activity.",
                "fraud_alert": self._alert_result(resolved),
                "outcome": "CUSTOMER_RECOGNIZED",
                "voided_authorizations": [],
                "provisional_credits": [],
                "replacement_card": None,
                "secure_message": {"thread_id": message.thread_id, "message_id": message.message_id},
                "escalated": False,
            }
            self.repo.complete_case_action(action_id=workflow_action.id, status="SUCCEEDED", result_payload=result)
            self.db.commit()
            return result

        from services.credit_card import (
            apply_fraud_provisional_credit,
            issue_replacement_card,
            void_fraud_authorization_hold,
        )

        voided_authorizations = [
            void_fraud_authorization_hold(
                self.db,
                account_id=str(alert.credit_account_id),
                authorization_id=authorization_id,
                fraud_alert_id=str(alert.id),
            )
            for authorization_id in disputed_authorization_ids
        ]
        provisional_credits = [
            apply_fraud_provisional_credit(
                self.db,
                account_id=str(alert.credit_account_id),
                transaction_id=transaction_id,
                fraud_alert_id=str(alert.id),
            )
            for transaction_id in disputed_transaction_ids
        ]
        replacement_result = None
        if issue_replacement:
            replacement_result = issue_replacement_card(
                self.db,
                account_id=str(alert.credit_account_id),
                reason="CUSTOMER_FRAUD_REISSUE",
                fraud_alert_id=str(alert.id),
                compromised_card_id=str(alert.card_id),
            )

        provisional_credit_total = sum(item["credited_amount_cents"] for item in provisional_credits)
        void_total = sum(item["voided_amount_cents"] for item in voided_authorizations)
        message = self._send_triage_secure_message(
            auth_provider_uid=auth_provider_uid,
            alert=alert,
            message_body=self._build_pending_review_triage_message(
                alert=alert,
                voided_authorizations=voided_authorizations,
                provisional_credits=provisional_credits,
                replacement_result=replacement_result,
                escalated=escalate,
                disputed_authorization_ids=disputed_authorization_ids,
                disputed_transaction_ids=disputed_transaction_ids,
            ),
        )
        triaged = self.repo.mark_triaged(
            fraud_alert_id=alert.id,
            remediation_status="ESCALATED" if escalate else "PENDING_SPECIALIST_REVIEW",
            triage_summary=self._build_triage_summary(voided_authorizations, provisional_credits, replacement_result, escalate),
            selected_disputed_authorization_ids=disputed_authorization_ids,
            selected_disputed_transaction_ids=disputed_transaction_ids,
            provisional_credit_cents=provisional_credit_total,
            replacement_card_id=replacement_result["new_card_id"] if replacement_result else None,
            triage_message_thread_id=message.thread_id,
            triage_message_id=message.message_id,
        )
        triaged.status = "TRIAGED_PENDING_REVIEW"
        self.db.add(triaged)
        record_audit_event(
            self.db,
            "FRAUD_CASE_TRIAGED",
            {
                "fraud_alert_id": str(triaged.id),
                "correlation_id": str(triaged.id),
                "customer_id": str(triaged.customer_id),
                "credit_account_id": str(triaged.credit_account_id),
                "card_id": str(triaged.card_id),
                "outcome": triaged.remediation_status,
                "disputed_authorization_ids": disputed_authorization_ids,
                "disputed_transaction_ids": disputed_transaction_ids,
                "voided_authorization_cents": void_total,
                "provisional_credit_cents": provisional_credit_total,
                "replacement_card_id": replacement_result["new_card_id"] if replacement_result else None,
                "escalated": escalate,
            },
        )
        record_audit_event(
            self.db,
            "FRAUD_TRIAGE_MESSAGE_SENT",
            {
                "fraud_alert_id": str(triaged.id),
                "correlation_id": str(triaged.id),
                "customer_id": str(triaged.customer_id),
                "thread_id": message.thread_id,
                "message_id": message.message_id,
            },
        )
        result = {
            "success": True,
            "message": "Fraud case triaged and pending specialist review.",
            "fraud_alert": self._alert_result(triaged),
            "outcome": triaged.remediation_status,
            "voided_authorizations": voided_authorizations,
            "provisional_credits": provisional_credits,
            "replacement_card": replacement_result,
            "secure_message": {"thread_id": message.thread_id, "message_id": message.message_id},
            "escalated": escalate,
        }
        self.repo.complete_case_action(action_id=workflow_action.id, status="SUCCEEDED", result_payload=result)
        self.db.commit()
        return result

    @staticmethod
    def _build_customer_message(card_last_four: str, suspicious_transactions: list[dict]) -> str:
        lines = [
            f"We noticed suspicious transactions on your credit card ending in {card_last_four}.",
            "Please review these recent purchases:",
        ]
        for txn in suspicious_transactions:
            amount = txn["amount_cents"] / 100
            lines.append(f"- {txn['merchant_name']}: ${amount:,.2f}")
        lines.append("If you did not make these purchases, chat now with a credit card support agent at /support/voice?entry=fraud-alert.")
        lines.append("If you recognize these purchases, acknowledge them in secure messaging so we can close the fraud alert.")
        return "\n".join(lines)

    def _send_triage_secure_message(self, *, auth_provider_uid: str, alert, message_body: str):
        message_request = SecureMessageCreateRequest(
            category="Fraud Alert",
            message=message_body,
            thread_id=alert.message_thread_id,
            user_id=auth_provider_uid,
            sender=SENDER_TYPE_BANK,
        )
        return self.messaging.create_message(
            message_request,
            ValidatedToken(claims={"sub": auth_provider_uid, "email": auth_provider_uid}),
        )

    @staticmethod
    def _alert_result(alert) -> dict:
        return {
            "fraud_alert_id": str(alert.id),
            "status": alert.status,
            "remediation_status": alert.remediation_status,
            "card_id": str(alert.card_id),
            "card_last_four": alert.card_last_four,
            "triaged_at": alert.triaged_at.isoformat() if alert.triaged_at else None,
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
        }

    @staticmethod
    def _build_triage_idempotency_key(
        *,
        disputed_authorization_ids: list[str],
        disputed_transaction_ids: list[str],
        issue_replacement: bool,
        escalate: bool,
    ) -> str:
        auth_part = ",".join(sorted(disputed_authorization_ids)) or "none"
        tx_part = ",".join(sorted(disputed_transaction_ids)) or "none"
        replacement_part = "replace" if issue_replacement else "no-replace"
        escalation_part = "escalate" if escalate else "no-escalate"
        key_material = f"{auth_part}:{tx_part}:{replacement_part}:{escalation_part}"
        key_digest = hashlib.sha256(key_material.encode("utf-8")).hexdigest()[:32]
        return f"triage:{key_digest}:{replacement_part}:{escalation_part}"

    @staticmethod
    def _format_cents(amount_cents: int) -> str:
        return f"${amount_cents / 100:,.2f}"

    def _build_recognized_triage_message(self, alert) -> str:
        return "\n".join(
            [
                f"Your fraud alert for card ending in {alert.card_last_four} has been marked as recognized activity.",
                "No credits, card replacement, or fraud investigation actions were applied.",
                "Thank you for reviewing the alert.",
            ]
        )

    def _build_pending_review_triage_message(
        self,
        *,
        alert,
        voided_authorizations: list[dict],
        provisional_credits: list[dict],
        replacement_result: dict | None,
        escalated: bool,
        disputed_authorization_ids: list[str],
        disputed_transaction_ids: list[str],
    ) -> str:
        lines = [
            f"Your fraud case for card ending in {alert.card_last_four} is now pending review by our fraud specialist team.",
        ]
        suspicious_transactions = alert.suspicious_transactions or []
        disputed_authorization_ids = set(disputed_authorization_ids or [])
        disputed_transaction_ids = set(disputed_transaction_ids or [])
        disputed_lines = [
            f"- {txn.get('merchant_name', 'Unknown merchant')}: {self._format_cents(int(txn.get('amount_cents') or 0))}"
            for txn in suspicious_transactions
            if txn.get("authorization_id") in disputed_authorization_ids
            or txn.get("transaction_id") in disputed_transaction_ids
        ]
        if disputed_lines:
            lines.append("Disputed transactions:")
            lines.extend(disputed_lines)
        if voided_authorizations:
            total = sum(item["voided_amount_cents"] for item in voided_authorizations)
            lines.append(f"We released pending authorization holds totaling {self._format_cents(total)}.")
        if provisional_credits:
            total = sum(item["credited_amount_cents"] for item in provisional_credits)
            lines.append(f"We applied provisional credits totaling {self._format_cents(total)} pending the full fraud investigation.")
        if replacement_result:
            lines.append(f"We issued a replacement virtual card ending in {replacement_result['new_last_four']}.")
        if escalated:
            lines.append("A human fraud specialist has also been asked to review the case.")
        lines.append("These actions remain pending the final fraud investigation outcome.")
        return "\n".join(lines)

    @staticmethod
    def _build_triage_summary(
        voided_authorizations: list[dict],
        provisional_credits: list[dict],
        replacement_result: dict | None,
        escalated: bool,
    ) -> str:
        parts = []
        if voided_authorizations:
            parts.append(f"{len(voided_authorizations)} pending authorization(s) reversed")
        if provisional_credits:
            parts.append(f"{len(provisional_credits)} provisional credit(s) applied")
        if replacement_result:
            parts.append("replacement virtual card issued")
        if escalated:
            parts.append("human fraud specialist review requested")
        return "; ".join(parts) or "Fraud case triaged"

    @staticmethod
    def _build_voice_context_summary(card_last_four: str, suspicious_transactions: list[dict]) -> str:
        if not suspicious_transactions:
            return f"Customer has an active fraud alert on card ending in {card_last_four}."
        top_merchants = ", ".join(txn["merchant_name"] for txn in suspicious_transactions[:3])
        return (
            f"Customer has an active fraud alert on card ending in {card_last_four}. "
            f"Recent suspicious transactions include {top_merchants}."
        )
