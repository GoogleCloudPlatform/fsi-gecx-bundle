from types import SimpleNamespace

from google.adk.agents.run_config import StreamingMode
from google.adk.tools.base_tool import BaseTool
from google.genai import types

from agent.live_runtime import build_live_run_config, normalize_live_event
from agent.tooling import configure_live_tool


class StubTool(BaseTool):
    def __init__(self) -> None:
        super().__init__(name="stub", description="stub tool")


def transcription(text: str, *, finished: bool = True) -> SimpleNamespace:
    return SimpleNamespace(text=text, finished=finished)


def live_event(**overrides) -> SimpleNamespace:
    values = {
        "input_transcription": None,
        "output_transcription": None,
        "actions": None,
        "interrupted": False,
        "turn_complete_reason": None,
        "live_session_resumption_update": None,
        "is_final_response": lambda: False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_build_audio_run_config_enables_transparent_resumption() -> None:
    config = build_live_run_config(
        mode="audio",
        avatar_name="Sam",
        voice_name="Aoede",
        language_code="en-US",
        enable_session_resumption=True,
    )

    assert config.streaming_mode is StreamingMode.BIDI
    assert config.response_modalities == ["AUDIO"]
    assert config.avatar_config is None
    assert config.session_resumption is not None
    assert config.session_resumption.transparent is True
    assert config.speech_config.language_code == "en-US"
    assert config.speech_config.voice_config.prebuilt_voice_config.voice_name == "Aoede"


def test_build_video_run_config_can_disable_resumption() -> None:
    config = build_live_run_config(
        mode="video",
        avatar_name="Sam",
        voice_name="Charon",
        language_code="en-US",
        enable_session_resumption=False,
    )

    assert config.response_modalities == ["VIDEO"]
    assert config.avatar_config.avatar_name == "Sam"
    assert config.session_resumption is None
    assert config.realtime_input_config is None


def test_build_video_run_config_supports_manual_activity_detection() -> None:
    config = build_live_run_config(
        mode="video",
        avatar_name="Ingrid",
        voice_name="Despina",
        language_code="en-GB",
        enable_session_resumption=True,
        manual_activity_detection=True,
    )

    assert config.response_modalities == ["VIDEO"]
    assert config.realtime_input_config is not None
    assert config.realtime_input_config.automatic_activity_detection.disabled is True


def test_audio_run_config_keeps_server_activity_detection() -> None:
    config = build_live_run_config(
        mode="audio",
        avatar_name=None,
        voice_name="Aoede",
        language_code="en-US",
        enable_session_resumption=True,
    )

    assert config.response_modalities == ["AUDIO"]
    assert config.realtime_input_config is None


def test_normalize_live_event_keeps_only_completed_transcripts() -> None:
    event = live_event(
        input_transcription=transcription("yes, please"),
        output_transcription=transcription("partial", finished=False),
        interrupted=True,
        actions=SimpleNamespace(end_of_agent=True),
        turn_complete_reason="STOP",
        live_session_resumption_update=SimpleNamespace(new_handle="resume-123"),
        is_final_response=lambda: True,
    )

    normalized = normalize_live_event(event)

    assert normalized.input_transcript == "yes, please"
    assert normalized.output_transcript is None
    assert normalized.final_response is True
    assert normalized.interrupted is True
    assert normalized.end_of_agent is True
    assert normalized.turn_complete_reason == "STOP"
    assert normalized.session_resumption_handle == "resume-123"


def test_configure_live_tool_defers_response_until_model_is_idle() -> None:
    tool = configure_live_tool(StubTool())

    assert tool.response_scheduling is types.FunctionResponseScheduling.WHEN_IDLE


def test_configure_live_tool_can_interrupt_preview_avatar_with_result() -> None:
    tool = configure_live_tool(
        StubTool(),
        response_scheduling=types.FunctionResponseScheduling.INTERRUPT,
    )

    assert tool.response_scheduling is types.FunctionResponseScheduling.INTERRUPT
