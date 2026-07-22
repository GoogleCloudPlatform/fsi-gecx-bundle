# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

"""Trusted, bounded session bootstrap for CES Gemini Live consultations."""

from __future__ import annotations

from dataclasses import dataclass
import uuid

from sqlalchemy.orm import Session

from repositories.accounts import AccountsRepository
from services.fraud_alerts import FraudAlertService
from utils.log_safety import stable_log_reference


CES_RUNTIME_NAME = "CES_GEMINI_LIVE"
DEFAULT_LANGUAGE_CODE = "en"
DEFAULT_RUNTIME_LANGUAGE_CODE = "en-US"
DEFAULT_LANGUAGE_SELECTION_SOURCE = "default"
MAX_GUIDANCE_SUMMARY_LENGTH = 8_000


class CesSessionBootstrapError(ValueError):
    """Trusted CES session context could not be established."""


@dataclass(frozen=True)
class CesSessionBootstrap:
    support_session_id: str
    runtime_name: str
    runtime_session_id: str
    customer_identity: str
    customer_id: str
    customer_ref: str
    reset_generation: str
    catalog_snapshot_id: str | None
    catalog_content_version: str | None
    entry_reason: str
    has_active_fraud_alert: bool
    guidance_summary: str
    ces_app_id: str
    ces_version_or_deployment_id: str
    language_code: str = DEFAULT_LANGUAGE_CODE
    runtime_language_code: str = DEFAULT_RUNTIME_LANGUAGE_CODE
    language_selection_source: str = DEFAULT_LANGUAGE_SELECTION_SOURCE

    def ces_variables(self, *, session_capability: str) -> dict:
        """Return declared, bounded CES variables sent before ``sys.welcome``."""
        return {
            "session_capability": session_capability,
            "support_session_id": self.support_session_id,
            "runtime_name": self.runtime_name,
            "runtime_session_id": self.runtime_session_id,
            "customer_ref": self.customer_ref,
            "reset_generation": self.reset_generation,
            "catalog_snapshot_id": self.catalog_snapshot_id or "",
            "catalog_content_version": self.catalog_content_version or "",
            "entry_reason": self.entry_reason,
            "has_active_fraud_alert": self.has_active_fraud_alert,
            "fraud_support_guidance_summary": self.guidance_summary[
                :MAX_GUIDANCE_SUMMARY_LENGTH
            ],
            "ces_app_id": self.ces_app_id,
            "ces_version_or_deployment_id": self.ces_version_or_deployment_id,
            "language_code": self.language_code,
            "runtime_language_code": self.runtime_language_code,
            "language_selection_source": self.language_selection_source,
        }


def _ces_resource_identity(resource_name: str) -> tuple[str, str]:
    value = str(resource_name or "").strip()
    if not value:
        raise CesSessionBootstrapError("CES application configuration is missing.")
    parts = value.split("/")
    if "apps" in parts:
        app_index = parts.index("apps")
        if app_index + 1 >= len(parts) or not parts[app_index + 1]:
            raise CesSessionBootstrapError("CES application resource is malformed.")
        app_id = parts[app_index + 1]
        if "deployments" in parts:
            deployment_index = parts.index("deployments")
            if deployment_index + 1 >= len(parts) or not parts[deployment_index + 1]:
                raise CesSessionBootstrapError("CES deployment resource is malformed.")
            return app_id, parts[deployment_index + 1]
        return app_id, "UNPINNED_APP"
    if "/" in value:
        raise CesSessionBootstrapError("CES application resource is malformed.")
    return value, "UNPINNED_APP"


def build_ces_session_bootstrap(
    db: Session,
    *,
    auth_provider_uid: str,
    runtime_session_id: str,
    gecx_app_id: str,
    support_session_id: str | None = None,
) -> CesSessionBootstrap:
    """Resolve one authenticated customer and build immutable session context."""
    identity = str(auth_provider_uid or "").strip()
    if not identity:
        raise CesSessionBootstrapError("Authenticated customer identity is missing.")
    app_id, version_or_deployment_id = _ces_resource_identity(gecx_app_id)
    user = AccountsRepository(db).get_user_by_auth_provider_uid(identity)
    if user is None:
        raise CesSessionBootstrapError(
            "Authenticated identity does not resolve to a banking customer."
        )

    runtime_session_id = str(runtime_session_id or "").strip()
    if not runtime_session_id:
        raise CesSessionBootstrapError("CES runtime session id is missing.")

    voice_context = FraudAlertService(db).get_active_voice_context(
        auth_provider_uid=identity
    )
    reset_generation = voice_context.get("reset_generation") or {}
    reset_token = str(reset_generation.get("token") or "").strip()
    if not reset_token:
        raise CesSessionBootstrapError("Voice reset generation is missing.")
    guidance = voice_context.get("support_guidance") or {}

    return CesSessionBootstrap(
        support_session_id=(
            str(support_session_id or "").strip() or f"ces-support-{uuid.uuid4().hex}"
        ),
        runtime_name=CES_RUNTIME_NAME,
        runtime_session_id=runtime_session_id,
        customer_identity=identity,
        customer_id=str(user.id),
        customer_ref=stable_log_reference(identity, "customer"),
        reset_generation=reset_token,
        catalog_snapshot_id=(str(guidance.get("snapshot_id") or "").strip() or None),
        catalog_content_version=(
            str(guidance.get("content_version") or "").strip() or None
        ),
        entry_reason=str(voice_context.get("entry_reason") or "general_support"),
        has_active_fraud_alert=bool(voice_context.get("has_active_fraud_alert", False)),
        guidance_summary=str(guidance.get("agent_guidance_summary") or ""),
        ces_app_id=app_id,
        ces_version_or_deployment_id=version_or_deployment_id,
    )
