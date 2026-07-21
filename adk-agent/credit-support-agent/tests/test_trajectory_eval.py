import pytest

from agent.trajectory_eval import (
    TrajectoryExpectation,
    compare_trajectory_outcomes,
    evaluate_trajectory,
)


def golden_events():
    return [
        {"type": "SESSION_STARTED", "reset_generation": "0:4", "elapsed_ms": 0},
        {
            "type": "GUIDANCE_SNAPSHOT",
            "source": "knowledge_catalog",
            "topic_ids": ["fraud_golden_path"],
            "elapsed_ms": 20,
        },
        {"type": "TOOL_CALL", "tool": "get_open_fraud_alert", "elapsed_ms": 30},
        {
            "type": "TOOL_RESULT",
            "tool": "get_open_fraud_alert",
            "success": True,
            "elapsed_ms": 60,
        },
        {"type": "TOOL_CALL", "tool": "triage_fraud_case", "elapsed_ms": 200},
        {
            "type": "TOOL_RESULT",
            "tool": "triage_fraud_case",
            "success": True,
            "elapsed_ms": 260,
        },
        {
            "type": "UI_EVENT",
            "event": "FRAUD_ALERT_RESOLVED",
            "elapsed_ms": 270,
        },
        {
            "type": "SUCCESS_CLAIM",
            "tool": "triage_fraud_case",
            "elapsed_ms": 300,
        },
        {
            "type": "SESSION_ENDED",
            "outcome": "NORMAL_DISCONNECT",
            "elapsed_ms": 500,
        },
    ]


def test_golden_trajectory_passes() -> None:
    result = evaluate_trajectory(
        golden_events(),
        TrajectoryExpectation(
            required_tools={"get_open_fraud_alert": 1, "triage_fraud_case": 1},
            required_ui_events=("FRAUD_ALERT_RESOLVED",),
        ),
    )

    assert result.passed is True
    assert result.metrics["guidance_source"] == "knowledge_catalog"
    assert result.metrics["duration_ms"] == 500


def test_duplicate_mutation_and_early_claim_fail() -> None:
    events = golden_events()
    events.insert(
        4,
        {
            "type": "SUCCESS_CLAIM",
            "tool": "triage_fraud_case",
            "elapsed_ms": 150,
        },
    )
    events.insert(
        -1,
        {"type": "TOOL_CALL", "tool": "triage_fraud_case", "elapsed_ms": 350},
    )
    result = evaluate_trajectory(
        events,
        TrajectoryExpectation(
            required_tools={"get_open_fraud_alert": 1, "triage_fraud_case": 1},
            required_ui_events=("FRAUD_ALERT_RESOLVED",),
        ),
    )

    assert result.passed is False
    assert any("more than once" in failure for failure in result.failures)
    assert any("claimed before" in failure for failure in result.failures)


def test_wallet_decline_forbids_wallet_tool() -> None:
    result = evaluate_trajectory(
        golden_events(),
        TrajectoryExpectation(
            required_tools={"get_open_fraud_alert": 1, "triage_fraud_case": 1},
            forbidden_tools=("push_card_to_google_wallet",),
            required_ui_events=("FRAUD_ALERT_RESOLVED",),
        ),
    )

    assert result.passed is True


def test_customer_reported_fraud_alternate_path_passes() -> None:
    events = golden_events()
    events[2:6] = [
        {"type": "TOOL_CALL", "tool": "get_open_fraud_alert", "elapsed_ms": 30},
        {
            "type": "TOOL_RESULT",
            "tool": "get_open_fraud_alert",
            "success": True,
            "elapsed_ms": 60,
        },
        {"type": "TOOL_CALL", "tool": "get_transaction_history", "elapsed_ms": 80},
        {
            "type": "TOOL_RESULT",
            "tool": "get_transaction_history",
            "success": True,
            "elapsed_ms": 100,
        },
        {
            "type": "TOOL_CALL",
            "tool": "triage_customer_reported_fraud",
            "elapsed_ms": 200,
        },
        {
            "type": "TOOL_RESULT",
            "tool": "triage_customer_reported_fraud",
            "success": True,
            "elapsed_ms": 260,
        },
    ]
    events = [
        event
        for event in events
        if event.get("tool") != "triage_fraud_case"
    ]
    result = evaluate_trajectory(
        events,
        TrajectoryExpectation(
            required_tools={
                "get_open_fraud_alert": 1,
                "get_transaction_history": 1,
                "triage_customer_reported_fraud": 1,
            },
            required_ui_events=("FRAUD_ALERT_RESOLVED",),
        ),
    )

    assert result.passed is True


def test_failures_name_dependency_tool_ui_and_terminal_layers() -> None:
    result = evaluate_trajectory(
        [
            {"type": "SESSION_STARTED", "elapsed_ms": 0},
            {"type": "TOOL_CALL", "tool": "triage_fraud_case", "elapsed_ms": 10},
            {
                "type": "TOOL_RESULT",
                "tool": "triage_fraud_case",
                "success": False,
                "elapsed_ms": 20,
            },
            {"type": "SESSION_ENDED", "outcome": "MODEL_FAILURE", "elapsed_ms": 30},
        ],
        TrajectoryExpectation(
            required_tools={"triage_fraud_case": 1},
            required_ui_events=("FRAUD_ALERT_RESOLVED",),
        ),
    )

    assert result.passed is False
    assert any("successful triage_fraud_case" in failure for failure in result.failures)
    assert any("UI event" in failure for failure in result.failures)
    assert any("guidance snapshot" in failure for failure in result.failures)
    assert any("reset generation" in failure for failure in result.failures)
    assert any("terminal outcome MODEL_FAILURE" in failure for failure in result.failures)
    assert result.metrics["tool_failures"] == 1


def proposal_confirmation_events(classification: str) -> list[dict]:
    return [
        {"type": "TRANSCRIPT", "author": "customer", "text": "selected charges", "elapsed_ms": 70},
        {"type": "ACTION_PROPOSAL", "outcome": "PROPOSED", "proposal_ref": "proposal_1", "elapsed_ms": 80},
        {"type": "TRANSCRIPT", "author": "agent", "text": "Please confirm the exact summary", "elapsed_ms": 90},
        {"type": "ACTION_PROPOSAL", "outcome": "PRESENTED", "proposal_ref": "proposal_1", "elapsed_ms": 100},
        {"type": "TRANSCRIPT", "author": "customer", "text": classification.lower(), "elapsed_ms": 110},
        {"type": "ACTION_PROPOSAL", "outcome": classification, "proposal_ref": "proposal_1", "elapsed_ms": 120},
    ]


def proposal_trajectory(
    classification: str = "CONFIRMED",
    *,
    commit_success: bool | None = True,
    terminal_proposal_outcome: str | None = "COMMITTED",
) -> list[dict]:
    events = golden_events()[:4]
    events.extend(proposal_confirmation_events(classification))
    if commit_success is not None:
        events.extend(
            [
                {"type": "TOOL_CALL", "tool": "commit_fraud_triage", "elapsed_ms": 130},
                {
                    "type": "TOOL_RESULT",
                    "tool": "commit_fraud_triage",
                    "success": commit_success,
                    "elapsed_ms": 160,
                },
            ]
        )
    if terminal_proposal_outcome:
        events.append(
            {
                "type": "ACTION_PROPOSAL",
                "outcome": terminal_proposal_outcome,
                "banking_outcome": (
                    "CONFIRMED_FRAUD_REMEDIATED"
                    if terminal_proposal_outcome in {"COMMITTED", "DIRECT_COMPLETED"}
                    else None
                ),
                "proposal_ref": "proposal_1",
                "elapsed_ms": 170,
            }
        )
    if commit_success:
        events.append(
            {"type": "UI_EVENT", "event": "FRAUD_ALERT_RESOLVED", "elapsed_ms": 180}
        )
    events.append(
        {"type": "SESSION_ENDED", "outcome": "NORMAL_DISCONNECT", "elapsed_ms": 200}
    )
    return events


def test_explicit_yes_proposal_trajectory_passes() -> None:
    result = evaluate_trajectory(
        proposal_trajectory(),
        TrajectoryExpectation(
            required_tools={"get_open_fraud_alert": 1, "commit_fraud_triage": 1},
            forbidden_tools=("triage_fraud_case",),
            required_ui_events=("FRAUD_ALERT_RESOLVED",),
            required_proposal_outcomes=("PROPOSED", "PRESENTED", "CONFIRMED", "COMMITTED"),
            expected_banking_outcome="CONFIRMED_FRAUD_REMEDIATED",
        ),
    )

    assert result.passed is True


@pytest.mark.parametrize("classification", ["DECLINED", "UNCLEAR"])
def test_non_authorizing_transcript_never_commits(classification: str) -> None:
    result = evaluate_trajectory(
        proposal_trajectory(
            classification,
            commit_success=None,
            terminal_proposal_outcome=None,
        ),
        TrajectoryExpectation(
            required_tools={"get_open_fraud_alert": 1},
            forbidden_tools=("commit_fraud_triage", "triage_fraud_case"),
            required_proposal_outcomes=("PROPOSED", "PRESENTED", classification),
        ),
    )

    assert result.passed is True


def test_interruption_invalidates_without_commit() -> None:
    events = proposal_trajectory(
        "INVALIDATED", commit_success=None, terminal_proposal_outcome=None
    )
    events.insert(-1, {"type": "INTERRUPTION", "elapsed_ms": 125})
    result = evaluate_trajectory(
        events,
        TrajectoryExpectation(
            required_tools={"get_open_fraud_alert": 1},
            forbidden_tools=("commit_fraud_triage", "triage_fraud_case"),
            required_proposal_outcomes=("PROPOSED", "INVALIDATED"),
        ),
    )

    assert result.passed is True
    assert result.metrics["interruptions"] == 1


@pytest.mark.parametrize("terminal_outcome", ["EXPIRED", "INVALIDATED"])
def test_expiry_and_reset_fail_closed(terminal_outcome: str) -> None:
    result = evaluate_trajectory(
        proposal_trajectory(
            commit_success=False,
            terminal_proposal_outcome=terminal_outcome,
        ),
        TrajectoryExpectation(
            required_tools={"get_open_fraud_alert": 1},
            required_failed_tools={"commit_fraud_triage": 1},
            forbidden_tools=("triage_fraud_case",),
            required_proposal_outcomes=("PROPOSED", "PRESENTED", terminal_outcome),
        ),
    )

    assert result.passed is True


def test_changed_selection_invalidates_old_proposal_before_new_commit() -> None:
    events = proposal_trajectory()
    presented_index = next(
        index
        for index, event in enumerate(events)
        if event.get("type") == "ACTION_PROPOSAL" and event.get("outcome") == "PRESENTED"
    )
    events[presented_index:presented_index] = [
        {"type": "ACTION_PROPOSAL", "outcome": "INVALIDATED", "proposal_ref": "proposal_old", "elapsed_ms": 91},
        {"type": "ACTION_PROPOSAL", "outcome": "PROPOSED", "proposal_ref": "proposal_1", "elapsed_ms": 92},
    ]
    result = evaluate_trajectory(
        events,
        TrajectoryExpectation(
            required_tools={"get_open_fraud_alert": 1, "commit_fraud_triage": 1},
            required_proposal_outcomes=("INVALIDATED", "CONFIRMED", "COMMITTED"),
            required_ui_events=("FRAUD_ALERT_RESOLVED",),
        ),
    )

    assert result.passed is True


def test_duplicate_commit_is_rejected_by_trajectory_contract() -> None:
    events = proposal_trajectory()
    events.insert(-2, {"type": "TOOL_CALL", "tool": "commit_fraud_triage", "elapsed_ms": 175})
    events.insert(-2, {"type": "TOOL_RESULT", "tool": "commit_fraud_triage", "success": True, "elapsed_ms": 176})
    result = evaluate_trajectory(
        events,
        TrajectoryExpectation(
            required_tools={"get_open_fraud_alert": 1, "commit_fraud_triage": 1},
            required_ui_events=("FRAUD_ALERT_RESOLVED",),
        ),
    )

    assert result.passed is False
    assert any("more than once" in failure for failure in result.failures)


def test_tool_failure_is_a_bounded_expected_trajectory() -> None:
    events = proposal_trajectory(
        commit_success=False, terminal_proposal_outcome="TOOL_ERROR"
    )
    result = evaluate_trajectory(
        events,
        TrajectoryExpectation(
            required_tools={"get_open_fraud_alert": 1},
            required_failed_tools={"commit_fraud_triage": 1},
            required_proposal_outcomes=("PROPOSED", "PRESENTED", "CONFIRMED", "TOOL_ERROR"),
        ),
    )

    assert result.passed is True
    assert result.metrics["tool_failures"] == 1


def test_direct_and_proposal_banking_outcomes_compare_equal() -> None:
    proposal = evaluate_trajectory(
        proposal_trajectory(),
        TrajectoryExpectation(
            required_tools={"get_open_fraud_alert": 1, "commit_fraud_triage": 1},
            required_ui_events=("FRAUD_ALERT_RESOLVED",),
        ),
    )
    direct_events = golden_events()
    direct_events.insert(
        -1,
        {
            "type": "ACTION_PROPOSAL",
            "outcome": "DIRECT_COMPLETED",
            "banking_outcome": "CONFIRMED_FRAUD_REMEDIATED",
            "elapsed_ms": 450,
        },
    )
    direct = evaluate_trajectory(
        direct_events,
        TrajectoryExpectation(
            required_tools={"get_open_fraud_alert": 1, "triage_fraud_case": 1},
            required_ui_events=("FRAUD_ALERT_RESOLVED",),
        ),
    )

    comparison = compare_trajectory_outcomes(direct, proposal)
    assert comparison.matched is True
    assert comparison.mismatches == ()
