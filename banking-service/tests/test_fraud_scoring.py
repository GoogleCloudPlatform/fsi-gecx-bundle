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
