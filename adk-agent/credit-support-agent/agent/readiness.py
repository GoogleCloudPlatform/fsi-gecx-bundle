"""Non-mutating dependency checks for the deployed voice-support runtime."""

from __future__ import annotations

import os
from typing import Any

import httpx
from sqlalchemy import text

from agent.session_store import get_session_service


async def _probe_session_store() -> dict[str, Any]:
    service = await get_session_service()
    engine = getattr(service, "db_engine", None)
    if engine is None:
        return {"ok": True, "backend": type(service).__name__, "durable": False}
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return {"ok": True, "backend": type(service).__name__, "durable": True}


async def _probe_http(
    *, url: str, headers: dict[str, str], accepted_statuses: set[int]
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:
        response = await client.get(url, headers=headers)
    return {
        "ok": response.status_code in accepted_statuses,
        "status": response.status_code,
    }


async def build_readiness_report(
    *,
    runtime_config,
    banking_service_url: str,
    banking_service_mcp_url: str,
    authorization_header: str | None,
    customer_probe=None,
    deployment_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a bounded report without exposing credentials or customer data."""
    checks: dict[str, dict[str, Any]] = {
        "configuration": {
            "ok": bool(
                runtime_config.audio_model
                and runtime_config.livekit_url
                and banking_service_url
                and banking_service_mcp_url
            ),
            "audio_model_configured": bool(runtime_config.audio_model),
            "video_model_configured": bool(runtime_config.video_model),
            "audio_model": runtime_config.audio_model,
            "video_model": runtime_config.video_model,
            "session_capacity": runtime_config.max_concurrent_sessions,
            "live_session_resumption": os.getenv(
                "VOICE_AGENT_SESSION_RESUMPTION_ENABLED", "true"
            ).lower()
            in {"1", "true", "yes", "on"},
            "durable_session_persistence": os.getenv(
                "VOICE_SESSION_PERSISTENCE_ENABLED", "true"
            ).lower()
            in {"1", "true", "yes", "on"},
        }
    }
    try:
        checks["session_store"] = await _probe_session_store()
    except Exception as error:
        checks["session_store"] = {
            "ok": False,
            "error": type(error).__name__,
        }

    headers = {"Authorization": authorization_header} if authorization_header else {}
    try:
        checks["mcp"] = await _probe_http(
            url=banking_service_mcp_url,
            headers=headers,
            accepted_statuses={200, 405, 406},
        )
    except Exception as error:
        checks["mcp"] = {"ok": False, "error": type(error).__name__}

    if customer_probe is not None:
        try:
            probe = await customer_probe()
            guidance = probe.support_guidance or {}
            active_fraud = bool(
                probe.voice_context.get("has_active_fraud_alert")
            )
            reset_generation_present = bool(
                (probe.voice_context.get("reset_generation") or {}).get("token")
            )
            guidance_available = bool(
                guidance.get("source") and guidance.get("topic_ids")
            )
            checks["customer_context"] = {
                "ok": reset_generation_present
                and (guidance_available if active_fraud else True),
                "active_fraud": active_fraud,
                "guidance_source": guidance.get("source"),
                "guidance_topics": guidance.get("topic_ids", []),
                "guidance_version": guidance.get("content_version"),
                "freshness": (guidance.get("freshness") or {}).get("status"),
                "reset_generation_present": reset_generation_present,
            }
        except Exception as error:
            checks["customer_context"] = {
                "ok": False,
                "error": type(error).__name__,
            }

    return {
        "status": "ready" if all(item.get("ok") for item in checks.values()) else "not_ready",
        "deployment": deployment_metadata or {},
        "checks": checks,
    }
