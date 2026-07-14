from agent import reset_guard
import pytest


class _Response:
    def __init__(self, token="3:7", status_error=False):
        self.token = token
        self.status_error = status_error

    def raise_for_status(self):
        if self.status_error:
            raise RuntimeError("unavailable")

    def json(self):
        return {"reset_generation": {"token": self.token}}


class _Client:
    response = _Response()

    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, *args, **kwargs):
        return self.response


@pytest.mark.asyncio
async def test_reset_guard_accepts_current_generation(monkeypatch):
    monkeypatch.setattr(reset_guard.httpx, "AsyncClient", _Client)
    assert await reset_guard.validate_reset_generation(
        banking_service_url="http://banking", headers={}, expected_token="3:7"
    ) == (True, "CURRENT")


@pytest.mark.asyncio
async def test_reset_guard_fails_closed_on_generation_change(monkeypatch):
    monkeypatch.setattr(reset_guard.httpx, "AsyncClient", _Client)
    valid, reason = await reset_guard.validate_reset_generation(
        banking_service_url="http://banking", headers={}, expected_token="3:8"
    )
    assert valid is False
    assert reason == "SESSION_INVALIDATED_BY_RESET"
