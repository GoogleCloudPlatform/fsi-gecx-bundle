from types import SimpleNamespace
from unittest.mock import MagicMock

from services.fraud_alerts import FraudAlertService


def service_with_alert():
    service = FraudAlertService(MagicMock())
    service.repo = MagicMock()
    service.repo.get_latest_open_alert_for_customer.return_value = SimpleNamespace(
        id="alert-1",
        suspicious_authorization_ids=["auth-1", "auth-2"],
        suspicious_transactions=[],
    )
    return service


def test_uncertain_and_partial_reviews_never_authorize_a_proposal():
    service = service_with_alert()

    uncertain = service.review_open_alert_selection(
        auth_provider_uid="customer-1",
        fraud_alert_id="alert-1",
        selection_status="UNCERTAIN",
    )
    partial = service.review_open_alert_selection(
        auth_provider_uid="customer-1",
        fraud_alert_id="alert-1",
        selection_status="PARTIAL",
        disputed_authorization_ids=["auth-1"],
    )

    assert uncertain["stage"] == "CLARIFYING_SELECTION"
    assert uncertain["ready_to_propose"] is False
    assert partial["stage"] == "CLARIFYING_SELECTION"
    assert partial["remaining_item_count"] == 1
    assert partial["ready_to_propose"] is False


def test_complete_review_requires_non_overlapping_full_coverage():
    service = service_with_alert()

    incomplete = service.review_open_alert_selection(
        auth_provider_uid="customer-1",
        fraud_alert_id="alert-1",
        selection_status="COMPLETE",
        disputed_authorization_ids=["auth-1"],
    )
    conflict = service.review_open_alert_selection(
        auth_provider_uid="customer-1",
        fraud_alert_id="alert-1",
        selection_status="COMPLETE",
        disputed_authorization_ids=["auth-1"],
        recognized_authorization_ids=["auth-1", "auth-2"],
    )
    complete = service.review_open_alert_selection(
        auth_provider_uid="customer-1",
        fraud_alert_id="alert-1",
        selection_status="COMPLETE",
        disputed_authorization_ids=["auth-1"],
        recognized_authorization_ids=["auth-2"],
    )

    assert incomplete["error"] == "FRAUD_SELECTION_INCOMPLETE"
    assert conflict["error"] == "CONFLICTING_FRAUD_SELECTION"
    assert complete["stage"] == "READY_TO_PROPOSE"
    assert complete["ready_to_propose"] is True
    assert len(complete["selection_fingerprint"]) == 64


def test_changed_selection_has_a_different_fingerprint():
    service = service_with_alert()
    first = service.review_open_alert_selection(
        auth_provider_uid="customer-1",
        fraud_alert_id="alert-1",
        selection_status="COMPLETE",
        disputed_authorization_ids=["auth-1"],
        recognized_authorization_ids=["auth-2"],
    )
    changed = service.review_open_alert_selection(
        auth_provider_uid="customer-1",
        fraud_alert_id="alert-1",
        selection_status="COMPLETE",
        disputed_authorization_ids=["auth-2"],
        recognized_authorization_ids=["auth-1"],
    )

    assert first["selection_fingerprint"] != changed["selection_fingerprint"]
