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

    @staticmethod
    def _build_customer_message(card_last_four: str, suspicious_transactions: list[dict]) -> str:
        lines = [
            f"We noticed suspicious transactions on your credit card ending in {card_last_four}.",
            "Please review these recent purchases:",
        ]
        for txn in suspicious_transactions:
            amount = txn["amount_cents"] / 100
            lines.append(f"- {txn['merchant_name']}: ${amount:,.2f}")
        lines.append("If you did not make these purchases, chat now with a credit card support agent at /support/voice.")
        return "\n".join(lines)

    @staticmethod
    def _build_voice_context_summary(card_last_four: str, suspicious_transactions: list[dict]) -> str:
        if not suspicious_transactions:
            return f"Customer has an active fraud alert on card ending in {card_last_four}."
        top_merchants = ", ".join(txn["merchant_name"] for txn in suspicious_transactions[:3])
        return (
            f"Customer has an active fraud alert on card ending in {card_last_four}. "
            f"Recent suspicious transactions include {top_merchants}."
        )
