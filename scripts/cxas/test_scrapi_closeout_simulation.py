"""Focused tests for SCRAPI closeout trajectory diagnostics."""

from scrapi_closeout_simulation import (
    _credit_limit_test_case,
    _strict_closeout_checks,
)


def test_credit_limit_scenario_does_not_repeat_initial_request() -> None:
    scenario = _credit_limit_test_case()

    assert len(scenario["steps"]) == 2
    assert scenario["steps"][0]["goal"].startswith("Confirm")


def test_strict_closeout_accepts_native_terminal_call() -> None:
    result = _strict_closeout_checks(
        [
            "User: No, that's all.",
            "Agent Transfer: Transferred to Session Closeout Agent",
            "Agent Text: You're very welcome. Goodbye.",
            "Tool Call: end_session with args "
            "{'reason': 'customer_query_ended'}",
        ]
    )

    assert result["passed"] is True


def test_strict_closeout_does_not_interpret_customer_wording() -> None:
    result = _strict_closeout_checks(
        [
            "User: That takes care of it for me, thank you.",
            "Agent Text: You're very welcome. Goodbye.",
            "User Query: That takes care of it for me thank you",
            "Agent Transfer: Transferred to Session Closeout Agent",
            "Tool Call: end_session with args "
            "{'reason': 'customer_query_ended'}",
        ]
    )

    assert result["passed"] is True


def test_strict_closeout_rejects_missing_native_terminal_call() -> None:
    result = _strict_closeout_checks(
        [
            "User: No, that's all.",
            "Agent Transfer: Transferred to Session Closeout Agent",
            "Agent Text: You're very welcome. Goodbye.",
        ]
    )

    assert result["passed"] is False
    assert result["checks"]["end_session_observed"] is False
