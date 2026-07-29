from pathlib import Path

from agent.fraud_voice import (
    build_fraud_playbook,
    build_initial_greeting,
    build_triage_model_result,
    mark_fraud_tool_completed,
    validate_fraud_tool_sequence,
)
from agent.instructions import compose_session_instruction


def _active_playbook() -> dict:
    return build_fraud_playbook(
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


def test_build_fraud_playbook_defaults_to_general_support() -> None:
    playbook = build_fraud_playbook(
        {"has_active_fraud_alert": False, "fraud_alert": None}
    )

    assert playbook["entry_mode"] == "GENERAL_SUPPORT"
    assert playbook["must_inspect_open_alert_first"] is False
    assert playbook["fraud_alert_id"] is None


def test_build_fraud_playbook_uses_alert_context() -> None:
    playbook = _active_playbook()

    assert playbook["entry_mode"] == "FRAUD_ALERT"
    assert playbook["must_inspect_open_alert_first"] is True
    assert playbook["fraud_alert_id"] == "fraud-123"
    assert playbook["card_last_four"] == "4242"
    assert playbook["suspicious_transactions_count"] == 2


def test_build_initial_greeting_acknowledges_fraud_context() -> None:
    greeting = build_initial_greeting(_active_playbook())

    assert "suspicious activity alert" in greeting
    assert "4242" in greeting
    assert "inspect the open fraud alert" in greeting


def test_validate_fraud_tool_sequence_requires_alert_inspection_first() -> None:
    error = validate_fraud_tool_sequence(
        _active_playbook(),
        "commit_fraud_triage",
        {"fraud_alert_id": "fraud-123"},
    )

    assert error == "Inspect the open fraud alert before taking mitigation actions."


def test_validate_fraud_tool_sequence_blocks_legacy_direct_actions() -> None:
    playbook = _active_playbook()
    playbook["open_alert_inspected"] = True

    for tool_name in (
        "report_lost_stolen_card",
        "issue_replacement_card_tool",
        "push_card_to_google_wallet",
    ):
        assert "typed proposal and commit workflow" in validate_fraud_tool_sequence(
            playbook, tool_name, {}
        )


def test_wallet_commit_requires_replacement_and_is_exactly_once() -> None:
    playbook = _active_playbook()
    assert (
        validate_fraud_tool_sequence(playbook, "commit_wallet_provisioning", {})
        == "Complete fraud triage and replacement before queueing Google Wallet provisioning."
    )

    playbook["replacement_issued"] = True
    assert (
        validate_fraud_tool_sequence(playbook, "commit_wallet_provisioning", {})
        is None
    )
    playbook["wallet_push_queued"] = True
    assert "already been queued" in validate_fraud_tool_sequence(
        playbook, "commit_wallet_provisioning", {}
    )


def test_triage_model_result_exposes_only_confirmed_outcomes() -> None:
    result = build_triage_model_result(
        {
            "message": "Fraud case triaged and pending specialist review.",
            "outcome": "PENDING_SPECIALIST_REVIEW",
            "voided_authorizations": [{"authorization_id": "auth-1"}],
            "provisional_credits": [],
            "replacement_card": {
                "is_virtual": True,
                "status": "ACTIVE",
                "new_last_four": "4447",
            },
            "secure_message": {"message_id": "message-1"},
            "escalated": False,
        }
    )

    assert result["pending_holds_released"] == 1
    assert result["provisional_credits_applied"] == 0
    assert result["replacement_card_last_four"] == "4447"
    assert result["secure_message_sent"] is True


def test_triage_rejects_wrong_alert_and_duplicate_execution() -> None:
    playbook = _active_playbook()
    playbook["open_alert_inspected"] = True

    assert "active fraud alert id" in validate_fraud_tool_sequence(
        playbook, "commit_fraud_triage", {"fraud_alert_id": "another-alert"}
    )
    playbook["triage_submitted"] = True
    assert "already been triaged" in validate_fraud_tool_sequence(
        playbook, "commit_fraud_triage", {"fraud_alert_id": "fraud-123"}
    )


def test_mark_fraud_tool_completed_tracks_commit_results() -> None:
    playbook = mark_fraud_tool_completed(
        _active_playbook(), "get_open_fraud_alert", {}
    )
    playbook = mark_fraud_tool_completed(
        playbook,
        "commit_fraud_triage",
        {
            "outcome": "PENDING_SPECIALIST_REVIEW",
            "replacement_card": {
                "new_card_id": "card-456",
                "new_card_token": "trusted-card-token",
            },
        },
    )
    playbook = mark_fraud_tool_completed(
        playbook,
        "commit_wallet_provisioning",
        {"wallet_provisioning_status": "QUEUED"},
    )

    assert playbook["resolution_completed"] is True
    assert playbook["replacement_issued"] is True
    assert playbook["replacement_card_token"] == "trusted-card-token"
    assert playbook["wallet_push_queued"] is True


def test_instruction_exposes_only_typed_consequential_action_protocol() -> None:
    text = (
        Path(__file__).parents[1] / "agent" / "resources" / "instruction.txt"
    ).read_text()

    assert "propose_card_reissue" in text
    assert "commit_card_reissue" in text
    assert "propose_wallet_provisioning" in text
    assert "commit_wallet_provisioning" in text
    assert "`report_lost_stolen_card`" not in text
    assert "`push_card_to_google_wallet`" not in text


def test_composed_fraud_instruction_preserves_catalog_grounding() -> None:
    instruction = compose_session_instruction(
        avatar_name="Nova",
        active_flows=["fraud_alert"],
        session_context="Trusted session context.",
        guidance_summary="Approved catalog guidance.",
    )

    assert "Active Fraud Alert Runtime Adapter" in instruction
    assert "Trusted session context." in instruction
    assert "Approved catalog guidance." in instruction
