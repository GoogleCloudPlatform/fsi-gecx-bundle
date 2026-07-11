import datetime

import httpx
import pytest
import respx

from scheduler import ScheduledEventRecord, dispatch_scheduled_event


class FakeScheduleClient:
    def __init__(self):
        self.marked_dispatching = False
        self.completed_payload = None

    async def mark_dispatching(self, event_record_id):
        self.marked_dispatching = True
        assert event_record_id == "event-record-1"
        return ScheduledEventRecord(
            id="event-record-1",
            schedule_id="schedule-1",
            scenario_id="scenario-1",
            execution_id="execution-1",
            event_id="auth-1",
            event_type="authorization",
            persona_id="persona-1",
            status="DISPATCHING",
            idempotency_key="schedule-1:auth-1",
            scheduled_for=datetime.datetime.now(datetime.timezone.utc),
            payload={
                "authorization_payload": {
                    "card_token": "tok_123",
                    "amount_cents": 4200,
                    "retrieval_reference_number": "123456789012",
                    "merchant_category_code": "5999",
                    "merchant_name": "TEST MERCHANT",
                    "card_network": "VISA",
                },
                "outcome_label": "false_positive",
            },
        )

    async def mark_succeeded(self, event_record_id, result_payload):
        self.completed_payload = result_payload
        return ScheduledEventRecord(
            id=event_record_id,
            schedule_id="schedule-1",
            scenario_id="scenario-1",
            execution_id="execution-1",
            event_id="auth-1",
            event_type="authorization",
            persona_id="persona-1",
            status="SUCCEEDED",
            idempotency_key="schedule-1:auth-1",
            scheduled_for=datetime.datetime.now(datetime.timezone.utc),
            result_payload=result_payload,
        )

    async def mark_failed(self, event_record_id, *, error, result_payload=None):
        raise AssertionError(f"unexpected failure: {error} {result_payload}")


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_scheduled_authorization_marks_success():
    banking_service_url = "https://banking.example"
    respx.post(f"{banking_service_url}/api/v1/card-network/authorize").mock(
        return_value=httpx.Response(
            200,
            json={
                "action_code": "00",
                "authorization_id": "auth-result-1",
                "fraud_alert_id": "alert-1",
                "fraud_risk_score": 72,
            },
        )
    )
    event = ScheduledEventRecord(
        id="event-record-1",
        schedule_id="schedule-1",
        scenario_id="scenario-1",
        execution_id="execution-1",
        event_id="auth-1",
        event_type="authorization",
        persona_id="persona-1",
        status="SCHEDULED",
        idempotency_key="schedule-1:auth-1",
        scheduled_for=datetime.datetime.now(datetime.timezone.utc),
    )
    schedule_client = FakeScheduleClient()

    result = await dispatch_scheduled_event(
        event=event,
        schedule_client=schedule_client,
        banking_service_url=banking_service_url,
        headers={"X-Card-Network-Token": "token"},
    )

    assert result.status == "SUCCEEDED"
    assert schedule_client.marked_dispatching is True
    assert schedule_client.completed_payload["authorization_id"] == "auth-result-1"
    assert schedule_client.completed_payload["fraud_alert_id"] == "alert-1"
