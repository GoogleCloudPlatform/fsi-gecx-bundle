"""Typed bootstrap coordination for one voice-support consultation."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import random
from typing import Any

import httpx

from agent.fraud_voice import build_fraud_playbook, build_initial_greeting

logger = logging.getLogger("voice_agent")


@dataclass(frozen=True)
class VoiceRuntimeSettings:
    mock_avatar_enabled: bool = False
    avatar_name: str = "Ben"
    max_duration: int = 300
    warning_duration: int = 240
    hard_timeout_enabled: bool = False


@dataclass(frozen=True)
class VoiceSessionBootstrap:
    settings: VoiceRuntimeSettings
    voice_context: dict[str, Any]
    fraud_playbook: dict[str, Any]
    support_guidance: dict[str, Any]
    initial_greeting_prompt: str


DEFAULT_GUIDANCE = {
    "schema_version": 1,
    "snapshot_id": None,
    "source": "none",
    "topic_ids": [],
    "content_version": None,
    "retrieved_at": None,
    "fallback_reason": "VOICE_CONTEXT_NOT_LOADED",
    "freshness": {"status": "UNKNOWN"},
    "topics": [],
    "agent_guidance_summary": "",
}


def default_session_bootstrap() -> VoiceSessionBootstrap:
    voice_context = {
        "has_active_fraud_alert": False,
        "fraud_alert": None,
        "reset_generation": {"global_epoch": 0, "customer_epoch": 0, "token": "0:0"},
    }
    playbook = build_fraud_playbook(voice_context)
    return VoiceSessionBootstrap(
        settings=VoiceRuntimeSettings(),
        voice_context=voice_context,
        fraud_playbook=playbook,
        support_guidance=dict(DEFAULT_GUIDANCE),
        initial_greeting_prompt=build_initial_greeting(playbook),
    )


def _parse_settings(payload: dict[str, Any]) -> VoiceRuntimeSettings:
    avatar_mode = str(payload.get("voice_agent_avatar_selection", "random"))
    avatar_name = (
        random.choice(["Ingrid", "Paul", "Sam"])
        if avatar_mode == "random"
        else avatar_mode
    )
    settings = VoiceRuntimeSettings(
        mock_avatar_enabled=payload.get("voice_agent_mock_avatar_enabled") == "true",
        avatar_name=avatar_name,
        max_duration=int(payload.get("voice_agent_max_duration", 300)),
        warning_duration=int(payload.get("voice_agent_warning_duration", 240)),
        hard_timeout_enabled=payload.get("voice_agent_hard_timeout_enabled") == "true",
    )
    if settings.warning_duration >= settings.max_duration:
        raise ValueError("voice warning duration must be less than maximum duration")
    return settings


async def load_session_bootstrap(
    *, banking_service_url: str, headers: dict[str, str]
) -> VoiceSessionBootstrap:
    voice_context: dict[str, Any] = {
        "has_active_fraud_alert": False,
        "fraud_alert": None,
        "reset_generation": {"global_epoch": 0, "customer_epoch": 0, "token": "0:0"},
    }
    settings = VoiceRuntimeSettings()
    guidance = dict(DEFAULT_GUIDANCE)
    async with httpx.AsyncClient(timeout=10.0) as client:
        settings_response = await client.get(
            f"{banking_service_url.rstrip('/')}/api/settings", headers=headers
        )
        settings_response.raise_for_status()
        settings = _parse_settings(settings_response.json())

        context_response = await client.get(
            f"{banking_service_url.rstrip('/')}/credit-card/voice/context",
            headers=headers,
        )
        context_response.raise_for_status()
        voice_context = context_response.json()
        guidance = voice_context.get("support_guidance") or guidance

    playbook = build_fraud_playbook(voice_context)
    return VoiceSessionBootstrap(
        settings=settings,
        voice_context=voice_context,
        fraud_playbook=playbook,
        support_guidance=guidance,
        initial_greeting_prompt=build_initial_greeting(playbook),
    )
