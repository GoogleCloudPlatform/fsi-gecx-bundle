"""Focused tests for SCRAPI closeout audio diagnostics."""

from scrapi_closeout_simulation import (
    CLOSEOUT_AGENT_NAME,
    _audio_completeness,
    _farewell_text,
    _strict_closeout_checks,
)


def _llm_record(audio_duration_ms: float) -> dict[str, object]:
    return {
        "agent": CLOSEOUT_AGENT_NAME,
        "model": "gemini-live",
        "audio_duration_ms": audio_duration_ms,
    }


def test_truncated_closeout_audio_fails() -> None:
    result = _audio_completeness(
        modality="audio",
        farewell_text="Thank you for banking with Nova Horizon. Goodbye.",
        llm_records=[_llm_record(960)],
    )

    assert result["passed"] is False
    assert result["observed_audio_ms"] == 960
    assert result["required_audio_ms"] == 1400


def test_complete_closeout_audio_passes() -> None:
    result = _audio_completeness(
        modality="audio",
        farewell_text="Thank you for banking with Nova Horizon. Goodbye.",
        llm_records=[_llm_record(2200)],
    )

    assert result["passed"] is True


def test_missing_closeout_telemetry_fails_audio_mode() -> None:
    result = _audio_completeness(
        modality="audio",
        farewell_text="Goodbye.",
        llm_records=[],
    )

    assert result["passed"] is False
    assert result["telemetry_observed"] is False


def test_text_mode_does_not_require_audio_telemetry() -> None:
    result = _audio_completeness(
        modality="text",
        farewell_text="Goodbye.",
        llm_records=[],
    )

    assert result["passed"] is True
    assert result["applicable"] is False


def test_farewell_text_is_extracted_from_terminal_trace() -> None:
    assert _farewell_text(
        [
            "Agent Transfer: Session Closeout Agent",
            "Agent Text [Session Closeout Agent]: You're very welcome. Goodbye.",
            "Tool Call [Session Closeout Agent]: end_session",
        ]
    ) == "You're very welcome. Goodbye."


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
