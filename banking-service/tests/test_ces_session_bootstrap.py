# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import uuid

import pytest

from services.ces_session_bootstrap import (
    MAX_GUIDANCE_SUMMARY_LENGTH,
    CesSessionBootstrapError,
    build_ces_session_bootstrap,
)


def voice_context(*, guidance_summary: str = "Follow the fraud playbook.") -> dict:
    return {
        "entry_reason": "fraud_alert",
        "has_active_fraud_alert": True,
        "reset_generation": {
            "global_epoch": 2,
            "customer_epoch": 4,
            "token": "2:4",
        },
        "support_guidance": {
            "snapshot_id": "snapshot-123",
            "content_version": "2.1",
            "agent_guidance_summary": guidance_summary,
        },
    }


@patch("services.ces_session_bootstrap.FraudAlertService")
@patch("services.ces_session_bootstrap.AccountsRepository")
def test_build_bootstrap_resolves_exact_identity_and_bounded_context(
    mock_accounts_repository, mock_fraud_alert_service
) -> None:
    customer_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    mock_accounts_repository.return_value.get_user_by_auth_provider_uid.return_value = (
        SimpleNamespace(id=customer_id)
    )
    mock_fraud_alert_service.return_value.get_active_voice_context.return_value = (
        voice_context()
    )

    bootstrap = build_ces_session_bootstrap(
        MagicMock(),
        auth_provider_uid="firebase-user-1",
        runtime_session_id="ces-runtime-1",
        support_session_id="support-session-1",
        gecx_app_id=(
            "projects/project-1/locations/us/apps/app-1/deployments/deployment-7"
        ),
    )

    assert bootstrap.customer_id == str(customer_id)
    assert bootstrap.support_session_id == "support-session-1"
    assert bootstrap.runtime_name == "CES_GEMINI_LIVE"
    assert bootstrap.runtime_session_id == "ces-runtime-1"
    assert bootstrap.customer_identity == "firebase-user-1"
    assert bootstrap.reset_generation == "2:4"
    assert bootstrap.catalog_snapshot_id == "snapshot-123"
    assert bootstrap.catalog_content_version == "2.1"
    assert bootstrap.ces_app_id == "app-1"
    assert bootstrap.ces_version_or_deployment_id == "deployment-7"
    assert bootstrap.language_code == "en"
    assert bootstrap.runtime_language_code == "en-US"
    mock_fraud_alert_service.return_value.get_active_voice_context.assert_called_once_with(
        auth_provider_uid="firebase-user-1"
    )


@patch("services.ces_session_bootstrap.FraudAlertService")
@patch("services.ces_session_bootstrap.AccountsRepository")
def test_build_bootstrap_rejects_unknown_identity_without_fallback(
    mock_accounts_repository, mock_fraud_alert_service
) -> None:
    mock_accounts_repository.return_value.get_user_by_auth_provider_uid.return_value = (
        None
    )

    with pytest.raises(CesSessionBootstrapError, match="does not resolve"):
        build_ces_session_bootstrap(
            MagicMock(),
            auth_provider_uid="unknown-user",
            runtime_session_id="ces-runtime-1",
            gecx_app_id="app-1",
        )

    mock_fraud_alert_service.assert_not_called()


@patch("services.ces_session_bootstrap.FraudAlertService")
@patch("services.ces_session_bootstrap.AccountsRepository")
def test_build_bootstrap_requires_reset_generation(
    mock_accounts_repository, mock_fraud_alert_service
) -> None:
    mock_accounts_repository.return_value.get_user_by_auth_provider_uid.return_value = (
        SimpleNamespace(id=uuid.uuid4())
    )
    context = voice_context()
    context["reset_generation"] = {}
    mock_fraud_alert_service.return_value.get_active_voice_context.return_value = (
        context
    )

    with pytest.raises(CesSessionBootstrapError, match="reset generation"):
        build_ces_session_bootstrap(
            MagicMock(),
            auth_provider_uid="firebase-user-1",
            runtime_session_id="ces-runtime-1",
            gecx_app_id="app-1",
        )


@patch("services.ces_session_bootstrap.FraudAlertService")
@patch("services.ces_session_bootstrap.AccountsRepository")
def test_ces_variables_are_declared_bounded_and_english_first(
    mock_accounts_repository, mock_fraud_alert_service
) -> None:
    mock_accounts_repository.return_value.get_user_by_auth_provider_uid.return_value = (
        SimpleNamespace(id=uuid.uuid4())
    )
    mock_fraud_alert_service.return_value.get_active_voice_context.return_value = (
        voice_context(guidance_summary="x" * (MAX_GUIDANCE_SUMMARY_LENGTH + 20))
    )
    bootstrap = build_ces_session_bootstrap(
        MagicMock(),
        auth_provider_uid="firebase-user-1",
        runtime_session_id="ces-runtime-1",
        gecx_app_id="app-1",
    )

    variables = bootstrap.ces_variables(session_capability="opaque-capability")

    assert variables["session_capability"] == "opaque-capability"
    assert "user_token" not in variables
    assert "access_token" not in variables
    assert len(variables["fraud_support_guidance_summary"]) == (
        MAX_GUIDANCE_SUMMARY_LENGTH
    )
    assert variables["ces_version_or_deployment_id"] == "UNPINNED_APP"
    assert variables["language_code"] == "en"
    assert variables["runtime_language_code"] == "en-US"
    assert variables["language_selection_source"] == "default"


def test_build_bootstrap_rejects_missing_ces_configuration() -> None:
    with pytest.raises(CesSessionBootstrapError, match="configuration is missing"):
        build_ces_session_bootstrap(
            MagicMock(),
            auth_provider_uid="firebase-user-1",
            runtime_session_id="ces-runtime-1",
            gecx_app_id="",
        )
