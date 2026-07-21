import importlib.util
from pathlib import Path

from agent.log_safety import stable_log_reference


SCRIPT = Path(__file__).parents[1] / "scripts" / "voice_canary.py"
SPEC = importlib.util.spec_from_file_location("voice_canary", SCRIPT)
voice_canary = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(voice_canary)


def entry(timestamp: str, message: str) -> dict:
    return {"timestamp": timestamp, "textPayload": message}


def json_entry(timestamp: str, payload: dict) -> dict:
    return {"timestamp": timestamp, "jsonPayload": payload}


def test_extract_deployed_trajectory() -> None:
    session = "11111111-1111-4111-8111-111111111111"
    session_ref = stable_log_reference(session, prefix="session")
    prefix = f"room_ref=room-ref session_ref={session_ref} mode=audio"
    entries = [
        entry(
            "2026-07-14T20:00:00Z",
            f"Opened ADK session state {prefix} reset_generation=0:3",
        ),
        entry(
            "2026-07-14T20:00:01Z",
            f"Loaded voice bootstrap {prefix} guidance_snapshot={{'source': 'knowledge_catalog', 'topic_ids': ['fraud_golden_path']}}",
        ),
        entry(
            "2026-07-14T20:00:02Z",
            f"[CALLBACK] before_tool_callback triggered {prefix} tool_name=triage_fraud_case args={{'keys': []}}",
        ),
        entry(
            "2026-07-14T20:00:03Z",
            f"[CALLBACK] after_tool_callback triggered {prefix} tool_name=triage_fraud_case result={{'success': True}}",
        ),
        entry(
            "2026-07-14T20:00:04Z",
            f"Broadcasting event to LiveKit data channel {prefix} event_type=FRAUD_ALERT_RESOLVED",
        ),
        entry(
            "2026-07-14T20:00:05Z",
            f"Cleaning up connections and tasks {prefix} terminal_outcome=NORMAL_DISCONNECT",
        ),
    ]

    found_session, events = voice_canary.extract_trajectory(entries)

    assert found_session == session_ref
    assert [event["type"] for event in events] == [
        "SESSION_STARTED",
        "GUIDANCE_SNAPSHOT",
        "TOOL_CALL",
        "TOOL_RESULT",
        "UI_EVENT",
        "SESSION_ENDED",
    ]
    assert events[1]["topic_ids"] == ["fraud_golden_path"]


def test_extract_deployed_trajectory_hashes_explicit_session_id() -> None:
    session = "11111111-1111-4111-8111-111111111111"
    session_ref = stable_log_reference(session, prefix="session")
    entries = [
        entry(
            "2026-07-14T20:00:00Z",
            "Opened ADK session state "
            f"session_ref={session_ref} reset_generation=0:3",
        ),
        entry(
            "2026-07-14T20:00:01Z",
            "Cleaning up connections and tasks "
            f"session_ref={session_ref} terminal_outcome=NORMAL_DISCONNECT",
        ),
    ]

    found_session, _ = voice_canary.extract_trajectory(
        entries, session_selector=session
    )

    assert found_session == session_ref


def test_non_error_checkpoint_is_a_successful_tool_result() -> None:
    session_ref = "session_c27700199f20"
    entries = [
        entry(
            "2026-07-14T20:00:00Z",
            f"Opened ADK session state session_ref={session_ref} reset_generation=0:3",
        ),
        entry(
            "2026-07-14T20:00:01Z",
            "[CALLBACK] before_tool_callback triggered "
            f"session_ref={session_ref} tool_name=prepare_fraud_triage_confirmation",
        ),
        entry(
            "2026-07-14T20:00:02Z",
            "[CALLBACK] after_tool_callback triggered "
            f"session_ref={session_ref} tool_name=prepare_fraud_triage_confirmation "
            "result={'is_error': False, 'structured': False}",
        ),
    ]

    _, events = voice_canary.extract_trajectory(entries, session_selector=session_ref)

    tool_result = next(event for event in events if event["type"] == "TOOL_RESULT")
    assert tool_result["success"] is True


def test_deployed_log_fetch_keeps_the_newest_sessions(monkeypatch) -> None:
    observed = {}

    def check_output(command, text):
        observed["command"] = command
        observed["text"] = text
        return "[]"

    monkeypatch.setattr(voice_canary.subprocess, "check_output", check_output)

    assert voice_canary.load_deployed_logs("demo-project", "us-central1", "15m") == []
    assert "--order=desc" in observed["command"]
    assert "--order=asc" not in observed["command"]
    assert observed["text"] is True


def test_extracts_normalized_proposal_event_for_same_hashed_session() -> None:
    session = "11111111-1111-4111-8111-111111111111"
    session_ref = stable_log_reference(session, prefix="session")
    entries = [
        entry(
            "2026-07-14T20:00:00Z",
            f"Opened ADK session state session_ref={session_ref} reset_generation=0:3",
        ),
        json_entry(
            "2026-07-14T20:00:01Z",
            {
                "message": "voice_action_proposal_event",
                "support_session_ref": session_ref,
                "proposal_ref": "proposal_abc123",
                "contract_version": "fraud-triage.v1",
                "tool": "commit_fraud_triage",
                "outcome": "COMMITTED",
                "banking_outcome": "CONFIRMED_FRAUD_REMEDIATED",
                "latency_ms": 125.0,
            },
        ),
        entry(
            "2026-07-14T20:00:02Z",
            f"Cleaning up connections and tasks session_ref={session_ref} terminal_outcome=NORMAL_DISCONNECT",
        ),
    ]

    _, events = voice_canary.extract_trajectory(entries, session_selector=session)

    proposal = next(event for event in events if event["type"] == "ACTION_PROPOSAL")
    assert proposal["proposal_ref"] == "proposal_abc123"
    assert proposal["outcome"] == "COMMITTED"
    assert proposal["banking_outcome"] == "CONFIRMED_FRAUD_REMEDIATED"


def test_canary_scenarios_use_proposal_commit_and_keep_direct_baseline() -> None:
    assert voice_canary.SCENARIOS["fraud"].required_tools["commit_fraud_triage"] == 1
    assert "triage_fraud_case" in voice_canary.SCENARIOS["fraud"].forbidden_tools
    assert voice_canary.SCENARIOS["fraud-direct"].required_tools["triage_fraud_case"] == 1
