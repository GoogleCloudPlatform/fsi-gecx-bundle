from fastapi.testclient import TestClient

from main import app
from models.authentication import ValidatedToken
from utils.auth import get_current_user


client = TestClient(app)


def _override_user(email: str):
    def current_user():
        return ValidatedToken(claims={"sub": "reset-operator", "email": email})

    return current_user


def test_full_reset_access_defaults_to_disabled(monkeypatch):
    monkeypatch.delenv("FULL_RESET_ENABLED", raising=False)
    app.dependency_overrides[get_current_user] = _override_user("admin@google.com")
    try:
        access = client.get("/internal/debug/reset-db/access")
        blocked = client.post("/internal/debug/reset-db")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert access.status_code == 200
    assert access.json()["allowed"] is False
    assert access.json()["reason"] == "FULL_RESET_DISABLED"
    assert blocked.status_code == 403
    assert "personal demo reset" in blocked.json()["detail"]


def test_full_reset_access_respects_operator_allowlist(monkeypatch):
    monkeypatch.setenv("FULL_RESET_ENABLED", "true")
    monkeypatch.setenv("FULL_RESET_OPERATOR_EMAILS", "owner@example.com,reset-admin@google.com")
    app.dependency_overrides[get_current_user] = _override_user("reset-admin@google.com")
    try:
        response = client.get("/internal/debug/reset-db/access")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    data = response.json()
    assert data["allowed"] is True
    assert data["operator_allowlist_configured"] is True
    assert data["reason"] == "ALLOWED"


def test_full_reset_access_blocks_non_allowlisted_operator(monkeypatch):
    monkeypatch.setenv("FULL_RESET_ENABLED", "true")
    monkeypatch.setenv("FULL_RESET_OPERATOR_EMAILS", "owner@example.com")
    app.dependency_overrides[get_current_user] = _override_user("admin@google.com")
    try:
        response = client.get("/internal/debug/reset-db/access")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert response.json()["allowed"] is False
    assert response.json()["reason"] == "OPERATOR_NOT_ALLOWLISTED"
