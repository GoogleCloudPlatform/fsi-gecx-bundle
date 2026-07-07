from sqlalchemy.orm import Session

from models.fraud import FraudAlert


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
