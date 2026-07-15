from agent.terminal_outcome import TerminalOutcome, ToolFailureTracker


def test_unresolved_tool_failure_has_distinct_terminal_outcome() -> None:
    tracker = ToolFailureTracker()
    tracker.record("push_card_to_google_wallet", "failure")

    assert (
        tracker.terminal_outcome(TerminalOutcome.NORMAL_DISCONNECT)
        == TerminalOutcome.TOOL_FAILURE
    )


def test_successful_same_tool_retry_resolves_failure() -> None:
    tracker = ToolFailureTracker()
    tracker.record("push_card_to_google_wallet", "error")
    tracker.record("push_card_to_google_wallet", "success")

    assert (
        tracker.terminal_outcome(TerminalOutcome.NORMAL_DISCONNECT)
        == TerminalOutcome.NORMAL_DISCONNECT
    )


def test_handoff_remains_primary_terminal_outcome() -> None:
    tracker = ToolFailureTracker()
    tracker.record("triage_fraud_case", "failure")

    assert (
        tracker.terminal_outcome(TerminalOutcome.HANDOFF)
        == TerminalOutcome.HANDOFF
    )
