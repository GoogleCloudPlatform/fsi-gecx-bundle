from agent.trajectory_eval import TrajectoryExpectation, evaluate_trajectory


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
