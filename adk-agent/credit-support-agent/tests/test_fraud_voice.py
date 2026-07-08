from agent.fraud_voice import build_fraud_playbook, build_initial_greeting


def test_build_fraud_playbook_defaults_to_general_support() -> None:
    playbook = build_fraud_playbook({"has_active_fraud_alert": False, "fraud_alert": None})

    assert playbook["entry_mode"] == "GENERAL_SUPPORT"
    assert playbook["must_inspect_open_alert_first"] is False
    assert playbook["fraud_alert_id"] is None


def test_build_fraud_playbook_uses_alert_context() -> None:
    playbook = build_fraud_playbook(
        {
            "has_active_fraud_alert": True,
            "fraud_alert": {
                "fraud_alert_id": "fraud-123",
                "card_last_four": "4242",
                "suspicious_transactions": [
                    {"merchant_name": "Acme Air", "amount_cents": 51000},
                    {"merchant_name": "Hotel Luna", "amount_cents": 23000},
                ],
            },
        }
    )

    assert playbook["entry_mode"] == "FRAUD_ALERT"
    assert playbook["must_inspect_open_alert_first"] is True
    assert playbook["fraud_alert_id"] == "fraud-123"
    assert playbook["card_last_four"] == "4242"
    assert playbook["suspicious_transactions_count"] == 2


def test_build_initial_greeting_acknowledges_fraud_context() -> None:
    greeting = build_initial_greeting(
        {
            "entry_mode": "FRAUD_ALERT",
            "card_last_four": "4242",
        }
    )

    assert "suspicious activity alert" in greeting
    assert "4242" in greeting
    assert "inspect the open fraud alert" in greeting


def test_build_initial_greeting_defaults_to_general_support() -> None:
    greeting = build_initial_greeting({"entry_mode": "GENERAL_SUPPORT"})

    assert "Credit Card Support Voice Assistant" in greeting
    assert "how you can help" in greeting
