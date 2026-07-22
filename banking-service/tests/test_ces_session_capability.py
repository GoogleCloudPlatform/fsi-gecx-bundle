from types import SimpleNamespace

import pytest

from services.ces_session_capability import (
    CesSessionCapabilityError,
    mint_ces_session_capability,
    validate_ces_session_capability,
)


SECRET = "test-secret-material-that-is-longer-than-thirty-two-bytes"


def _bootstrap():
    return SimpleNamespace(
        customer_identity="firebase-user-sensitive",
        customer_id="11111111-1111-1111-1111-111111111111",
        support_session_id="support-1",
        runtime_name="CES_GEMINI_LIVE",
        runtime_session_id="runtime-1",
        reset_generation="3:9",
        ces_app_id="app-1",
        ces_version_or_deployment_id="deployment-7",
    )


def _headers(**overrides):
    headers = {
        "x-support-session-id": "support-1",
        "x-runtime-name": "CES_GEMINI_LIVE",
        "x-runtime-session-id": "runtime-1",
        "x-reset-generation": "3:9",
        "x-ces-app-id": "app-1",
        "x-ces-version-or-deployment-id": "deployment-7",
    }
    headers.update(overrides)
    return headers


def test_capability_is_opaque_short_lived_and_session_bound(monkeypatch):
    monkeypatch.setenv("CES_SESSION_CAPABILITY_TTL_SECONDS", "900")
    token = mint_ces_session_capability(_bootstrap(), now=1_000, secret=SECRET)

    assert token.startswith("cescap1.")
    assert "firebase-user-sensitive" not in token
    assert "11111111-1111-1111-1111-111111111111" not in token
    claims = validate_ces_session_capability(
        token, _headers(), now=1_100, secret=SECRET
    )
    assert claims.customer_identity == "firebase-user-sensitive"
    assert claims.customer_id == "11111111-1111-1111-1111-111111111111"
    assert claims.expires_at == 1_900


def test_capability_rejects_expiry_and_header_rebinding(monkeypatch):
    monkeypatch.setenv("CES_SESSION_CAPABILITY_TTL_SECONDS", "900")
    token = mint_ces_session_capability(_bootstrap(), now=1_000, secret=SECRET)

    with pytest.raises(CesSessionCapabilityError, match="invalid or expired"):
        validate_ces_session_capability(token, _headers(), now=1_901, secret=SECRET)
    with pytest.raises(CesSessionCapabilityError, match="binding"):
        validate_ces_session_capability(
            token,
            _headers(**{"x-runtime-session-id": "attacker-session"}),
            now=1_100,
            secret=SECRET,
        )


def test_capability_rejects_tampering(monkeypatch):
    monkeypatch.setenv("CES_SESSION_CAPABILITY_TTL_SECONDS", "900")
    token = mint_ces_session_capability(_bootstrap(), now=1_000, secret=SECRET)
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")

    with pytest.raises(CesSessionCapabilityError, match="invalid or expired"):
        validate_ces_session_capability(tampered, _headers(), now=1_100, secret=SECRET)
