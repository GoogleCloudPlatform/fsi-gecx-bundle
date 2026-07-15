from pathlib import Path

from agent.agent import build_log_context
from agent.log_safety import (
    stable_log_reference,
    tool_args_log_summary,
    tool_response_is_expected_checkpoint,
    tool_response_succeeded,
    tool_result_log_summary,
)


def test_stable_log_reference_is_correlatable_without_exposing_value() -> None:
    first = stable_log_reference("jane.doe@example.com", prefix="customer")
    second = stable_log_reference("jane.doe@example.com", prefix="customer")

    assert first == second
    assert first.startswith("customer_")
    assert "jane" not in first


def test_agent_log_context_pseudonymizes_session_identifier() -> None:
    context = build_log_context(
        state={"session_id": "session-secret", "room_name": "room-secret"}
    )

    assert context["session_ref"].startswith("session_")
    assert "session_id" not in context
    assert "secret" not in str(context)


def test_tool_args_summary_omits_tokens_and_ids() -> None:
    summary = tool_args_log_summary(
        "push_card_to_google_wallet",
        {
            "card_token": "tok-secret",
            "session_id": "session-secret",
            "wallet_provider": "GOOGLE_WALLET",
        },
    )

    assert "tok-secret" not in str(summary)
    assert "session-secret" not in str(summary)
    assert summary["trusted_card_token_present"] is True
    assert summary["wallet_provider"] == "GOOGLE_WALLET"


def test_tool_result_summary_retains_outcomes_not_identifiers() -> None:
    summary = tool_result_log_summary(
        {
            "isError": False,
            "structuredContent": {
                "success": True,
                "outcome": "PENDING_SPECIALIST_REVIEW",
                "voided_authorizations": [{"authorization_id": "auth-secret"}],
                "replacement_card": {"new_card_token": "tok-secret"},
                "secure_message": {"thread_id": "thread-secret"},
            },
        }
    )

    assert summary["success"] is True
    assert summary["voided_authorization_count"] == 1
    assert summary["replacement_card_issued"] is True
    assert "secret" not in str(summary)


def test_tool_error_summary_never_logs_provider_controlled_message() -> None:
    summary = tool_result_log_summary(
        {"isError": True, "error": "failed for card tok-secret"}
    )

    assert summary["error_present"] is True
    assert "tok-secret" not in str(summary)


def test_no_open_alert_is_a_successful_tool_read() -> None:
    assert tool_response_succeeded(
        "get_open_fraud_alert",
        {
            "structuredContent": {
                "success": False,
                "fraud_alert": None,
                "support_guidance": {"source": "knowledge_catalog"},
            }
        },
    )


def test_failed_mutation_remains_a_tool_failure() -> None:
    assert not tool_response_succeeded(
        "push_card_to_google_wallet",
        {
            "structuredContent": {
                "success": False,
                "error": "PROVISIONING_FAILED",
            }
        },
    )


def test_direct_local_tool_success_is_recognized() -> None:
    assert tool_response_succeeded(
        "prepare_fraud_triage_confirmation",
        {"success": True, "confirmation_required": True},
    )


def test_control_checkpoint_is_not_a_tool_execution_failure() -> None:
    assert tool_response_is_expected_checkpoint(
        {
            "success": False,
            "isError": False,
            "status": "SESSION_CLOSE_CONFIRMATION_REQUIRED",
        }
    )


def test_voice_dispatch_identifiers_do_not_use_logged_query_strings() -> None:
    root = Path(__file__).resolve().parents[3]
    voice_runtime = (root / "adk-agent/credit-support-agent/voice_agent.py").read_text()
    capacity_probe = (
        root / "adk-agent/credit-support-agent/scripts/voice_capacity_probe.py"
    ).read_text()
    canary = (root / "adk-agent/credit-support-agent/scripts/voice_canary.py").read_text()
    banking_router = (root / "banking-service/routers/credit_card.py").read_text()

    assert "uvicorn.run(app, host=\"0.0.0.0\", port=port, access_log=False)" in voice_runtime
    assert 'json={\n                    "room_name": room_name' in capacity_probe
    assert 'json={\n                    "room_name": room_name' in banking_router
    assert 'headers = {"x-target-customer-id": customer_id}' in canary
