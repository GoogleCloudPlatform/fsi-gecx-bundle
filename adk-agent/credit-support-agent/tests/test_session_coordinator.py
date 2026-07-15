from agent.session_coordinator import should_abandon_escalation
from agent.terminal_outcome import TerminalOutcome


def test_successful_handoff_does_not_abandon_escalation() -> None:
    assert not should_abandon_escalation(
        "escalation-1", TerminalOutcome.HANDOFF
    )


def test_disconnect_before_handoff_abandons_escalation() -> None:
    assert should_abandon_escalation(
        "escalation-1", TerminalOutcome.NORMAL_DISCONNECT
    )


def test_no_active_escalation_needs_no_cleanup() -> None:
    assert not should_abandon_escalation(None, TerminalOutcome.MODEL_FAILURE)
