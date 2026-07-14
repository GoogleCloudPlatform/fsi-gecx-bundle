"""Fail-closed reset-generation validation for consequential tools."""

from __future__ import annotations

import httpx


async def validate_reset_generation(
    *, banking_service_url: str, headers: dict[str, str], expected_token: str
) -> tuple[bool, str]:
    if not expected_token:
        return False, "SESSION_RESET_GENERATION_MISSING"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{banking_service_url.rstrip('/')}/credit-card/voice/context",
                headers=headers,
            )
        response.raise_for_status()
        current = response.json().get("reset_generation") or {}
        if str(current.get("token") or "") != expected_token:
            return False, "SESSION_INVALIDATED_BY_RESET"
        return True, "CURRENT"
    except Exception:
        return False, "RESET_GENERATION_UNAVAILABLE"
