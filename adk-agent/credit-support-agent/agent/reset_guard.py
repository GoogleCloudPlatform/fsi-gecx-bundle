# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Fail-closed reset-generation validation for consequential tools."""

from __future__ import annotations

import asyncio
import logging

import httpx


logger = logging.getLogger("voice_agent")
RESET_CHECK_ATTEMPTS = 3


async def validate_reset_generation(
    *, banking_service_url: str, headers: dict[str, str], expected_token: str
) -> tuple[bool, str]:
    if not expected_token:
        return False, "SESSION_RESET_GENERATION_MISSING"
    for attempt in range(1, RESET_CHECK_ATTEMPTS + 1):
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
        except Exception as error:
            logger.warning(
                "Reset-generation check attempt failed attempt=%s/%s error_type=%s",
                attempt,
                RESET_CHECK_ATTEMPTS,
                type(error).__name__,
            )
            if attempt < RESET_CHECK_ATTEMPTS:
                await asyncio.sleep(0.1 * attempt)
    return False, "RESET_GENERATION_UNAVAILABLE"
