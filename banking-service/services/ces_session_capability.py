# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

"""Short-lived, encrypted authority for one CES banking session."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import hmac
import json
import os
import time
from typing import Mapping, TYPE_CHECKING

from cryptography.fernet import Fernet, InvalidToken

from utils.gcp import get_secret

if TYPE_CHECKING:
    from services.ces_session_bootstrap import CesSessionBootstrap


CAPABILITY_PREFIX = "cescap1."
CAPABILITY_VERSION = 1
CAPABILITY_ISSUER = "banking-service"
CAPABILITY_AUDIENCE = "banking-service:mcp"
DEFAULT_CAPABILITY_TTL_SECONDS = 900
DEFAULT_SECRET_ID = "ces-session-capability-key"


class CesSessionCapabilityError(PermissionError):
    """The supplied CES session capability is invalid or no longer current."""


@dataclass(frozen=True)
class CesSessionCapabilityClaims:
    customer_identity: str
    customer_id: str
    support_session_id: str
    runtime_name: str
    runtime_session_id: str
    reset_generation: str
    ces_app_id: str
    ces_version_or_deployment_id: str
    issued_at: int
    expires_at: int


def _ttl_seconds() -> int:
    value = int(
        os.getenv(
            "CES_SESSION_CAPABILITY_TTL_SECONDS",
            str(DEFAULT_CAPABILITY_TTL_SECONDS),
        )
    )
    if value < 60 or value > 3600:
        raise CesSessionCapabilityError("CES session capability TTL is invalid.")
    return value


def _secret_value(override: str | None = None) -> str:
    value = override or os.getenv("CES_SESSION_CAPABILITY_KEY")
    if not value:
        value = get_secret(
            os.getenv("CES_SESSION_CAPABILITY_SECRET_ID", DEFAULT_SECRET_ID)
        )
    value = str(value or "").strip()
    if len(value) < 32:
        raise CesSessionCapabilityError(
            "CES session capability signing material is invalid."
        )
    return value


def _fernet(override: str | None = None) -> Fernet:
    derived_key = hashlib.sha256(_secret_value(override).encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(derived_key))


def mint_ces_session_capability(
    bootstrap: "CesSessionBootstrap",
    *,
    now: int | None = None,
    secret: str | None = None,
) -> str:
    """Mint an encrypted capability bound to exactly one CES session."""
    issued_at = int(time.time() if now is None else now)
    expires_at = issued_at + _ttl_seconds()
    payload = {
        "v": CAPABILITY_VERSION,
        "iss": CAPABILITY_ISSUER,
        "aud": CAPABILITY_AUDIENCE,
        "iat": issued_at,
        "exp": expires_at,
        "customer_identity": bootstrap.customer_identity,
        "customer_id": bootstrap.customer_id,
        "support_session_id": bootstrap.support_session_id,
        "runtime_name": bootstrap.runtime_name,
        "runtime_session_id": bootstrap.runtime_session_id,
        "reset_generation": bootstrap.reset_generation,
        "ces_app_id": bootstrap.ces_app_id,
        "ces_version_or_deployment_id": bootstrap.ces_version_or_deployment_id,
    }
    encrypted = _fernet(secret).encrypt_at_time(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"),
        current_time=issued_at,
    )
    return CAPABILITY_PREFIX + encrypted.decode("ascii")


def _required_header(headers: Mapping[str, str], name: str) -> str:
    value = str(headers.get(name) or "").strip()
    if not value or len(value) > 512 or any(char in value for char in "\r\n"):
        raise CesSessionCapabilityError("CES session capability binding is invalid.")
    return value


def validate_ces_session_capability(
    token: str,
    headers: Mapping[str, str],
    *,
    now: int | None = None,
    secret: str | None = None,
) -> CesSessionCapabilityClaims:
    """Decrypt, expire, and bind a capability to trusted CES transport headers."""
    value = str(token or "").strip()
    if not value.startswith(CAPABILITY_PREFIX):
        raise CesSessionCapabilityError("CES session capability is invalid.")
    current_time = int(time.time() if now is None else now)
    try:
        raw = _fernet(secret).decrypt_at_time(
            value[len(CAPABILITY_PREFIX) :].encode("ascii"),
            ttl=_ttl_seconds(),
            current_time=current_time,
        )
        payload = json.loads(raw)
    except (
        InvalidToken,
        UnicodeError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        raise CesSessionCapabilityError(
            "CES session capability is invalid or expired."
        ) from exc

    if (
        payload.get("v") != CAPABILITY_VERSION
        or payload.get("iss") != CAPABILITY_ISSUER
        or payload.get("aud") != CAPABILITY_AUDIENCE
        or int(payload.get("exp") or 0) < current_time
    ):
        raise CesSessionCapabilityError("CES session capability is invalid or expired.")

    normalized = {str(key).lower(): str(value) for key, value in headers.items()}
    bindings = {
        "support_session_id": _required_header(normalized, "x-support-session-id"),
        "runtime_name": _required_header(normalized, "x-runtime-name"),
        "runtime_session_id": _required_header(normalized, "x-runtime-session-id"),
        "reset_generation": _required_header(normalized, "x-reset-generation"),
        "ces_app_id": _required_header(normalized, "x-ces-app-id"),
        "ces_version_or_deployment_id": _required_header(
            normalized, "x-ces-version-or-deployment-id"
        ),
    }
    for claim_name, header_value in bindings.items():
        if not hmac.compare_digest(str(payload.get(claim_name) or ""), header_value):
            raise CesSessionCapabilityError(
                "CES session capability binding is invalid."
            )

    customer_identity = str(payload.get("customer_identity") or "").strip()
    customer_id = str(payload.get("customer_id") or "").strip()
    if not customer_identity or not customer_id:
        raise CesSessionCapabilityError("CES session capability identity is invalid.")

    return CesSessionCapabilityClaims(
        customer_identity=customer_identity,
        customer_id=customer_id,
        support_session_id=bindings["support_session_id"],
        runtime_name=bindings["runtime_name"],
        runtime_session_id=bindings["runtime_session_id"],
        reset_generation=bindings["reset_generation"],
        ces_app_id=bindings["ces_app_id"],
        ces_version_or_deployment_id=bindings["ces_version_or_deployment_id"],
        issued_at=int(payload.get("iat") or 0),
        expires_at=int(payload.get("exp") or 0),
    )
