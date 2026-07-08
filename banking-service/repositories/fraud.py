import datetime

from sqlalchemy.orm import Session

from models.fraud import FraudAlert, FraudCaseAction


class FraudAlertRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_alert(
        self,
        *,
        customer_id,
        auth_provider_uid: str,
        credit_account_id,
        card_id,
        card_last_four: str,
        message_thread_id: str,
        suspicious_authorization_ids: list[str],
        suspicious_transactions: list[dict],
        source: str = "SIMULATION_TARGETED_FRAUD",
        status: str = "OPEN",
    ) -> FraudAlert:
        alert = FraudAlert(
            customer_id=customer_id,
            auth_provider_uid=auth_provider_uid,
            credit_account_id=credit_account_id,
            card_id=card_id,
            card_last_four=card_last_four,
            status=status,
            source=source,
            message_thread_id=message_thread_id,
            suspicious_authorization_ids=suspicious_authorization_ids,
            suspicious_transactions=suspicious_transactions,
        )
        self.db.add(alert)
        self.db.flush()
        return alert

    def get_latest_open_alert_for_customer(
        self,
        *,
        customer_id=None,
        auth_provider_uid: str | None = None,
    ) -> FraudAlert | None:
        query = self.db.query(FraudAlert).filter(FraudAlert.status == "OPEN")
        if customer_id is not None:
            query = query.filter(FraudAlert.customer_id == customer_id)
        elif auth_provider_uid:
            query = query.filter(FraudAlert.auth_provider_uid == auth_provider_uid)
        else:
            return None
        return query.order_by(FraudAlert.created_at.desc()).first()

    def get_open_alert_for_account(
        self,
        *,
        credit_account_id,
    ) -> FraudAlert | None:
        return (
            self.db.query(FraudAlert)
            .filter(
                FraudAlert.credit_account_id == credit_account_id,
                FraudAlert.status == "OPEN",
            )
            .order_by(FraudAlert.created_at.desc())
            .first()
        )

    def resolve_alert(
        self,
        *,
        fraud_alert_id,
        resolved_status: str,
    ) -> FraudAlert | None:
        alert = self.db.query(FraudAlert).filter(FraudAlert.id == fraud_alert_id).first()
        if not alert:
            return None
        alert.status = resolved_status
        alert.resolved_at = datetime.datetime.now(datetime.timezone.utc)
        self.db.add(alert)
        self.db.flush()
        return alert

    def mark_triaged(
        self,
        *,
        fraud_alert_id,
        remediation_status: str,
        triage_summary: str | None = None,
        selected_disputed_authorization_ids: list[str] | None = None,
        selected_disputed_transaction_ids: list[str] | None = None,
        provisional_credit_cents: int | None = None,
        replacement_card_id=None,
        triage_message_thread_id: str | None = None,
        triage_message_id: str | None = None,
    ) -> FraudAlert | None:
        alert = self.db.query(FraudAlert).filter(FraudAlert.id == fraud_alert_id).first()
        if not alert:
            return None

        alert.remediation_status = remediation_status
        alert.triaged_at = datetime.datetime.now(datetime.timezone.utc)
        alert.triage_summary = triage_summary
        if selected_disputed_authorization_ids is not None:
            alert.selected_disputed_authorization_ids = selected_disputed_authorization_ids
        if selected_disputed_transaction_ids is not None:
            alert.selected_disputed_transaction_ids = selected_disputed_transaction_ids
        if provisional_credit_cents is not None:
            alert.provisional_credit_cents = provisional_credit_cents
        if replacement_card_id is not None:
            alert.replacement_card_id = replacement_card_id
        if triage_message_thread_id is not None:
            alert.triage_message_thread_id = triage_message_thread_id
        if triage_message_id is not None:
            alert.triage_message_id = triage_message_id

        self.db.add(alert)
        self.db.flush()
        return alert

    def create_case_action(
        self,
        *,
        fraud_alert_id,
        action_type: str,
        status: str = "PENDING",
        idempotency_key: str | None = None,
        request_payload: dict | None = None,
        result_payload: dict | None = None,
        completed_at: datetime.datetime | None = None,
    ) -> FraudCaseAction:
        existing = None
        if idempotency_key:
            existing = self.get_case_action_by_idempotency_key(
                fraud_alert_id=fraud_alert_id,
                idempotency_key=idempotency_key,
            )
        if existing:
            return existing

        action = FraudCaseAction(
            fraud_alert_id=fraud_alert_id,
            action_type=action_type,
            status=status,
            idempotency_key=idempotency_key,
            request_payload=request_payload or {},
            result_payload=result_payload or {},
            completed_at=completed_at,
        )
        self.db.add(action)
        self.db.flush()
        return action

    def get_case_action_by_idempotency_key(
        self,
        *,
        fraud_alert_id,
        idempotency_key: str,
    ) -> FraudCaseAction | None:
        return (
            self.db.query(FraudCaseAction)
            .filter(
                FraudCaseAction.fraud_alert_id == fraud_alert_id,
                FraudCaseAction.idempotency_key == idempotency_key,
            )
            .first()
        )

    def list_case_actions(self, *, fraud_alert_id) -> list[FraudCaseAction]:
        return (
            self.db.query(FraudCaseAction)
            .filter(FraudCaseAction.fraud_alert_id == fraud_alert_id)
            .order_by(FraudCaseAction.created_at.asc())
            .all()
        )

    def complete_case_action(
        self,
        *,
        action_id,
        status: str,
        result_payload: dict | None = None,
    ) -> FraudCaseAction | None:
        action = self.db.query(FraudCaseAction).filter(FraudCaseAction.id == action_id).first()
        if not action:
            return None
        action.status = status
        action.result_payload = result_payload or {}
        action.completed_at = datetime.datetime.now(datetime.timezone.utc)
        self.db.add(action)
        self.db.flush()
        return action
