from agent.fraud_voice import (
    build_fraud_playbook,
    build_initial_greeting,
    mark_fraud_tool_completed,
    validate_fraud_tool_sequence,
)


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
            "suspicious_transactions_count": 2,
        }
    )

    assert "suspicious activity alert" in greeting
    assert "4242" in greeting
    assert "inspect the open fraud alert" in greeting
    assert "whether the customer recognizes the transactions" in greeting


def test_build_initial_greeting_defaults_to_general_support() -> None:
    greeting = build_initial_greeting({"entry_mode": "GENERAL_SUPPORT"})

    assert "Credit Card Support Voice Assistant" in greeting
    assert "how you can help" in greeting


def test_validate_fraud_tool_sequence_requires_alert_inspection_first() -> None:
    playbook = build_fraud_playbook(
        {
            "has_active_fraud_alert": True,
            "fraud_alert": {"fraud_alert_id": "fraud-123", "card_last_four": "4242"},
        }
    )

    error = validate_fraud_tool_sequence(playbook, "report_lost_stolen_card", {})

    assert error == "Inspect the open fraud alert before taking mitigation actions."


def test_validate_fraud_tool_sequence_requires_block_before_replacement() -> None:
    playbook = build_fraud_playbook(
        {
            "has_active_fraud_alert": True,
            "fraud_alert": {"fraud_alert_id": "fraud-123", "card_last_four": "4242"},
        }
    )
    playbook["open_alert_inspected"] = True

    error = validate_fraud_tool_sequence(playbook, "issue_replacement_card_tool", {})

    assert error == "Block the card before issuing a replacement card."


def test_validate_fraud_tool_sequence_requires_wallet_before_confirmed_resolution() -> None:
    playbook = build_fraud_playbook(
        {
            "has_active_fraud_alert": True,
            "fraud_alert": {"fraud_alert_id": "fraud-123", "card_last_four": "4242"},
        }
    )
    playbook["open_alert_inspected"] = True
    playbook["card_blocked"] = True
    playbook["replacement_issued"] = True

    error = validate_fraud_tool_sequence(
        playbook,
        "resolve_fraud_alert",
        {"resolution": "CUSTOMER_CONFIRMED_FRAUD"},
    )

    assert error == "Queue Google Wallet provisioning before resolving the alert as confirmed fraud."


def test_validate_fraud_tool_sequence_allows_recognized_resolution_after_inspection() -> None:
    playbook = build_fraud_playbook(
        {
            "has_active_fraud_alert": True,
            "fraud_alert": {"fraud_alert_id": "fraud-123", "card_last_four": "4242"},
        }
    )
    playbook["open_alert_inspected"] = True

    error = validate_fraud_tool_sequence(
        playbook,
        "resolve_fraud_alert",
        {"resolution": "CUSTOMER_RECOGNIZED"},
    )

    assert error is None


def test_mark_fraud_tool_completed_tracks_mitigation_progress() -> None:
    playbook = build_fraud_playbook(
        {
            "has_active_fraud_alert": True,
            "fraud_alert": {"fraud_alert_id": "fraud-123", "card_last_four": "4242"},
        }
    )

    playbook = mark_fraud_tool_completed(playbook, "get_open_fraud_alert", {"fraud_alert": {}})
    playbook = mark_fraud_tool_completed(playbook, "report_lost_stolen_card", {})
    playbook = mark_fraud_tool_completed(playbook, "issue_replacement_card_tool", {})
    playbook = mark_fraud_tool_completed(playbook, "push_card_to_google_wallet", {})
    playbook = mark_fraud_tool_completed(
        playbook,
        "resolve_fraud_alert",
        {"fraud_alert": {"resolution": "CUSTOMER_CONFIRMED_FRAUD"}},
    )

    assert playbook["open_alert_inspected"] is True
    assert playbook["card_blocked"] is True
    assert playbook["replacement_issued"] is True
    assert playbook["wallet_push_queued"] is True
    assert playbook["resolution_completed"] is True
    assert playbook["confirmed_fraud"] is True
