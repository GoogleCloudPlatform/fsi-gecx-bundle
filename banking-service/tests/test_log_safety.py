import logging
from types import SimpleNamespace

import pytest

from routers.mcp import utils as mcp_utils
from services.support import SupportService
from utils.log_safety import stable_log_reference


class _FakeDb:
    def commit(self):
        return None

    def rollback(self):
        return None


class _FakeSupportRepository:
    def save(self, escalation):
        escalation.id = "escalation-secret-123"
        return escalation


def test_stable_log_reference_is_correlatable_without_exposing_value():
    sensitive_value = "customer@example.com"

    first = stable_log_reference(sensitive_value, "customer")
    second = stable_log_reference(sensitive_value, "customer")

    assert first == second
    assert first.startswith("customer:")
    assert sensitive_value not in first


def test_escalation_logging_omits_customer_transcript_and_room(caplog):
    service = SupportService.__new__(SupportService)
    service.db = _FakeDb()
    service.repo = _FakeSupportRepository()
    payload = SimpleNamespace(
        escalation_id=None,
        room_name="room-sensitive-456",
        customer_id="customer-sensitive-789",
        reason="Customer disclosed a sensitive dispute",
        transcript=[{"text": "My card number is sensitive"}],
    )

    with caplog.at_level(logging.INFO, logger="services.support"):
        result = service.escalate_session(payload)

    log_output = caplog.text
    assert result == {
        "status": "SUCCESS",
        "escalation_id": "escalation-secret-123",
    }
    assert "room-sensitive-456" not in log_output
    assert "customer-sensitive-789" not in log_output
    assert "Customer disclosed a sensitive dispute" not in log_output
    assert "My card number is sensitive" not in log_output
    assert "room:" in log_output
    assert "customer:" in log_output


@pytest.mark.asyncio
async def test_mcp_authorization_logging_omits_headers_and_customer_id(
    caplog, monkeypatch
):
    bearer_token = "Bearer sensitive-oidc-token"
    customer_id = "customer-sensitive-123"
    context = SimpleNamespace(
        request_context=SimpleNamespace(
            request=SimpleNamespace(
                headers={
                    "Authorization": bearer_token,
                    "X-Target-Customer-Id": customer_id,
                }
            )
        )
    )
    monkeypatch.setattr(mcp_utils, "is_running_locally", lambda: True)

    @mcp_utils.requires_user_assertion
    async def protected_tool(*, ctx=None, verified_customer_id=None):
        return {"customer_id": verified_customer_id}

    with caplog.at_level(logging.INFO, logger="routers.mcp.utils"):
        result = await protected_tool(ctx=context)

    assert result == {"customer_id": customer_id}
    assert bearer_token not in caplog.text
    assert customer_id not in caplog.text
    assert "target_customer_ref=customer:" in caplog.text
