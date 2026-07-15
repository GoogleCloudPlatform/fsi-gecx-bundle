"""Central validation for voice runtime environment and session requests."""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class VoiceRuntimeConfig:
    audio_model: str | None
    video_model: str | None
    livekit_url: str
    max_concurrent_sessions: int
    audio_session_capacity_units: int = 1
    video_session_capacity_units: int = 4


def load_runtime_config() -> VoiceRuntimeConfig:
    max_sessions = int(os.getenv("VOICE_AGENT_MAX_CONCURRENT_SESSIONS", "10"))
    if max_sessions < 1:
        raise ValueError("VOICE_AGENT_MAX_CONCURRENT_SESSIONS must be positive")
    audio_units = int(os.getenv("VOICE_AGENT_AUDIO_SESSION_CAPACITY_UNITS", "1"))
    video_units = int(os.getenv("VOICE_AGENT_VIDEO_SESSION_CAPACITY_UNITS", "4"))
    if min(audio_units, video_units) < 1:
        raise ValueError("Voice session capacity units must be positive")
    livekit_url = os.getenv("LIVEKIT_URL", "ws://localhost:7880")
    if not livekit_url.startswith(("ws://", "wss://")):
        raise ValueError("LIVEKIT_URL must use ws:// or wss://")
    return VoiceRuntimeConfig(
        audio_model=os.getenv("VOICE_AGENT_AUDIO_MODEL"),
        video_model=os.getenv("VOICE_AGENT_VIDEO_MODEL"),
        livekit_url=livekit_url,
        max_concurrent_sessions=max_sessions,
        audio_session_capacity_units=audio_units,
        video_session_capacity_units=video_units,
    )


def validate_session_request(config: VoiceRuntimeConfig, *, mode: str) -> str:
    normalized_mode = mode.lower().strip()
    if normalized_mode not in {"audio", "video"}:
        raise ValueError("mode must be 'audio' or 'video'")
    if normalized_mode == "audio" and not config.audio_model:
        raise ValueError("VOICE_AGENT_AUDIO_MODEL is required for audio sessions")
    if normalized_mode == "video" and not config.video_model and not config.audio_model:
        raise ValueError("A video or audio fallback model is required for video sessions")
    return normalized_mode
