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


class _FlakyClient(_Client):
    attempts = 0

    async def get(self, *args, **kwargs):
        type(self).attempts += 1
        if type(self).attempts < 3:
            raise RuntimeError("transient")
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


@pytest.mark.asyncio
async def test_reset_guard_retries_transient_transport_failure(monkeypatch):
    _FlakyClient.attempts = 0
    monkeypatch.setattr(reset_guard.httpx, "AsyncClient", _FlakyClient)
    monkeypatch.setattr(reset_guard.asyncio, "sleep", lambda _delay: _no_op())

    assert await reset_guard.validate_reset_generation(
        banking_service_url="http://banking", headers={}, expected_token="3:7"
    ) == (True, "CURRENT")
    assert _FlakyClient.attempts == 3


async def _no_op():
    return None
