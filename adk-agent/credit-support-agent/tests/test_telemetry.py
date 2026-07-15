import json

from agent import telemetry


def test_structured_metric_is_low_cardinality_and_machine_readable(capsys) -> None:
    telemetry.record_tool_completed("triage_fraud_case", "success", 0.125)

    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    assert [event["metric"] for event in events] == [
        "voice.tool.calls",
        "voice.tool.duration",
    ]
    assert events[1]["value"] == 0.125
    assert events[1]["attributes"] == {
        "tool": "triage_fraud_case",
        "outcome": "success",
    }
    assert "customer" not in str(events)


def test_avatar_fallback_metric_has_bounded_reason(capsys) -> None:
    telemetry.record_avatar_fallback("decoder_stopped")

    event = json.loads(capsys.readouterr().out)

    assert event["metric"] == "voice.avatar.fallbacks"
    assert event["attributes"] == {"reason": "decoder_stopped"}
