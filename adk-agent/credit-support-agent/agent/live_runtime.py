"""ADK Live configuration and event normalization for the voice runtime."""

from __future__ import annotations

import os
from dataclasses import dataclass

from google.adk.agents.run_config import RunConfig, StreamingMode
from google.genai import types


def env_flag(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def build_live_run_config(
    *,
    mode: str,
    avatar_name: str | None,
    voice_name: str,
    language_code: str,
    enable_session_resumption: bool | None = None,
) -> RunConfig:
    """Build the single supported ADK 2.4 configuration for a voice session."""
    video_mode = mode == "video"
    if enable_session_resumption is None:
        enable_session_resumption = env_flag(
            "VOICE_AGENT_SESSION_RESUMPTION_ENABLED",
            default=True,
        )

    return RunConfig(
        streaming_mode=StreamingMode.BIDI,
        response_modalities=["VIDEO"] if video_mode else ["AUDIO"],
        avatar_config=(
            types.AvatarConfig(avatar_name=avatar_name)
            if video_mode and avatar_name
            else None
        ),
        speech_config=types.SpeechConfig(
            language_code=language_code,
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=voice_name
                )
            ),
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        session_resumption=(
            types.SessionResumptionConfig(transparent=True)
            if enable_session_resumption
            else None
        ),
    )


@dataclass(frozen=True)
class LiveEventView:
    """Application-level view of ADK Live event lifecycle fields."""

    input_transcript: str | None
    output_transcript: str | None
    final_response: bool
    interrupted: bool
    end_of_agent: bool
    turn_complete_reason: str | None
    session_resumption_handle: str | None


def normalize_live_event(event) -> LiveEventView:
    """Normalize ADK events without leaking version-specific checks downstream."""
    input_transcription = getattr(event, "input_transcription", None)
    output_transcription = getattr(event, "output_transcription", None)
    actions = getattr(event, "actions", None)
    resumption_update = getattr(event, "live_session_resumption_update", None)
    turn_complete_reason = getattr(event, "turn_complete_reason", None)

    return LiveEventView(
        input_transcript=(
            input_transcription.text
            if input_transcription and input_transcription.finished
            else None
        ),
        output_transcript=(
            output_transcription.text
            if output_transcription and output_transcription.finished
            else None
        ),
        final_response=bool(event.is_final_response()),
        interrupted=bool(getattr(event, "interrupted", False)),
        end_of_agent=bool(actions and actions.end_of_agent),
        turn_complete_reason=(
            str(turn_complete_reason) if turn_complete_reason is not None else None
        ),
        session_resumption_handle=(
            resumption_update.new_handle if resumption_update else None
        ),
    )

