import datetime
from types import SimpleNamespace

from services.fraud_scoring import FraudDecision, FraudScoringService


def test_evaluate_authorization_returns_deterministic_baseline_decision():
    payload = {
        "amount_cents": 1500,
        "merchant_category_code": "5812",
        "merchant_name": "Local Restaurant",
    }
    service = FraudScoringService()

    first = service.evaluate_authorization(payload)
    second = service.evaluate_authorization(payload)

    assert isinstance(first, FraudDecision)
    assert first == second
    assert first.score == 3
    assert first.threshold == 20
    assert first.decision == "APPROVED"
    assert first.reason_codes == ["BASELINE_LOW_RISK"]
    assert first.features["amount_cents"] == 1500
    assert first.features["merchant_category_code"] == "5812"
    assert first.model_version == "local-deterministic-v1"


def test_evaluate_authorization_honors_explicit_simulation_override():
    service = FraudScoringService()

    decision = service.evaluate_authorization(
        {
            "amount_cents": 125000,
            "merchant_category_code": "5947",
            "merchant_name": "RAZER GOLD GIFT CARD",
            "is_fraud_simulation": True,
            "risk_score": 91,
        }
    )

    assert decision.score == 91
    assert decision.decision == "FLAGGED"
    assert decision.reason_codes == ["EXPLICIT_SIMULATION_OVERRIDE"]
    assert decision.features["has_explicit_simulation_flag"] is True
    assert decision.features["has_risk_score_override"] is True


def test_evaluate_transaction_risk_remains_backward_compatible():
    service = FraudScoringService()

    score = service.evaluate_transaction_risk({"is_fraud_simulation": True})

    assert score == 85


def test_extract_authorization_features_handles_empty_history():
    service = FraudScoringService()

    features = service.extract_authorization_features(
        {"amount_cents": 2500, "merchant_category_code": "5411", "merchant_name": "GROCERY - CHICAGO IL"},
        context={"transaction_channel": "CARD_PRESENT", "merchant_country_code": "USA"},
    )

    assert features["recent_auth_count_10m"] == 0
    assert features["recent_auth_count_1h"] == 0
    assert features["recent_flagged_count_24h"] == 0
    assert features["amount_to_recent_average_ratio"] is None
    assert features["distance_from_recent_card_present_location"] is None
    assert features["transaction_channel"] == "CARD_PRESENT"


def test_extract_authorization_features_computes_velocity_amount_and_location():
    now = datetime.datetime(2026, 7, 10, 12, 0, tzinfo=datetime.timezone.utc)
    recent_authorizations = [
        SimpleNamespace(
            created_at=now - datetime.timedelta(minutes=5),
            transaction_amount_cents=1000,
            merchant_category_code="5947",
            status="PENDING",
            transaction_channel="CARD_PRESENT",
            merchant_latitude=37.7749,
            merchant_longitude=-122.4194,
        ),
        SimpleNamespace(
            created_at=now - datetime.timedelta(minutes=45),
            transaction_amount_cents=2000,
            merchant_category_code="5947",
            status="FLAGGED",
            transaction_channel="ECOMMERCE",
            merchant_latitude=None,
            merchant_longitude=None,
        ),
        SimpleNamespace(
            created_at=now - datetime.timedelta(hours=3),
            transaction_amount_cents=3000,
            merchant_category_code="5812",
            status="PENDING",
            transaction_channel="CARD_PRESENT",
            merchant_latitude=41.8781,
            merchant_longitude=-87.6298,
        ),
    ]
    account = SimpleNamespace(credit_limit_cents=100000, available_credit_cents=40000)
    service = FraudScoringService()

    features = service.extract_authorization_features(
        {
            "amount_cents": 9000,
            "merchant_category_code": "5947",
            "merchant_name": "RAZER GOLD GIFT CARD",
            "created_at": now,
        },
        context={
            "transaction_channel": "ECOMMERCE",
            "entry_mode": "ECOMMERCE",
            "merchant_country_code": "USA",
            "merchant_latitude": 34.0522,
            "merchant_longitude": -118.2437,
            "is_digital_goods": True,
        },
        recent_authorizations=recent_authorizations,
        account=account,
    )

    assert features["recent_auth_count_10m"] == 1
    assert features["recent_auth_count_1h"] == 2
    assert features["recent_flagged_count_24h"] == 1
    assert features["same_mcc_count_1h"] == 2
    assert features["amount_to_recent_average_ratio"] == 4.5
    assert features["distance_from_recent_card_present_location"] == 347.4
    assert features["minutes_since_last_card_present_location"] == 5.0
    assert features["credit_utilization_after_auth"] == 0.69
    assert features["available_credit_ratio"] == 0.4
    assert "GIFT_CARD" in features["descriptor_flags"]
    assert "GAMING" in features["descriptor_flags"]
    assert features["is_digital_goods"] is True
