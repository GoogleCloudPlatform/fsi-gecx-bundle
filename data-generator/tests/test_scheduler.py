import datetime

import httpx
import pytest
import respx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from scheduler import ScheduledEventRecord, SyntheticScheduleClient, dispatch_scheduled_event
from scheduler.database import Base
from scheduler.repository import SyntheticScheduledEventRepository


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


@pytest.fixture(name="scheduler_session")
def fixture_scheduler_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        execution_options={"schema_translate_map": {"operations": None}},
    )
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = testing_session_local()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_synthetic_scheduled_event_repository_idempotent_lifecycle(scheduler_session):
    repo = SyntheticScheduledEventRepository(scheduler_session)
    scheduled_for = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        minutes=5
    )

    first = repo.create_event(
        schedule_id="schedule-1",
        scenario_id="scenario-1",
        execution_id="execution-1",
        event_id="auth-1",
        event_type="authorization",
        persona_id="persona-1",
        scheduled_for=scheduled_for,
        idempotency_key="schedule-1:auth-1",
        payload={"amount_cents": 4200},
    )
    second = repo.create_event(
        schedule_id="schedule-1",
        event_id="auth-1-retry",
        event_type="authorization",
        scheduled_for=scheduled_for,
        idempotency_key="schedule-1:auth-1",
        payload={"amount_cents": 9999},
    )

    assert second.id == first.id
    assert second.event_id == "auth-1"

    dispatching = repo.mark_dispatching(first.id)
    assert dispatching.status == "DISPATCHING"
    assert dispatching.attempts == 1

    completed = repo.mark_succeeded(
        event_record_id=first.id,
        result_payload={"authorization_id": "auth-result-1"},
    )
    assert completed.status == "SUCCEEDED"
    assert completed.result_payload == {"authorization_id": "auth-result-1"}

    completed_context = repo.list_completed_before(
        schedule_id="schedule-1", persona_id="persona-1"
    )
    assert [event.id for event in completed_context] == [first.id]


def test_synthetic_scheduled_event_repository_cancels_future_events(scheduler_session):
    repo = SyntheticScheduledEventRepository(scheduler_session)
    now = datetime.datetime.now(datetime.timezone.utc)
    repo.create_event(
        schedule_id="schedule-cancel",
        event_id="future-auth",
        event_type="authorization",
        scheduled_for=now + datetime.timedelta(minutes=5),
        idempotency_key="schedule-cancel:future-auth",
    )
    repo.create_event(
        schedule_id="schedule-cancel",
        event_id="past-auth",
        event_type="authorization",
        scheduled_for=now - datetime.timedelta(minutes=5),
        idempotency_key="schedule-cancel:past-auth",
    )

    canceled = repo.cancel_future_events(schedule_id="schedule-cancel")
    events = repo.list_events(schedule_id="schedule-cancel")

    assert canceled == 1
    assert {event.event_id: event.status for event in events} == {
        "past-auth": "SCHEDULED",
        "future-auth": "CANCELED",
    }


@pytest.mark.asyncio
async def test_synthetic_schedule_client_uses_local_repository():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        execution_options={"schema_translate_map": {"operations": None}},
    )
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    client = SyntheticScheduleClient(session_factory=testing_session_local)
    scheduled_for = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        minutes=5
    )

    try:
        created = await client.create_event(
            {
                "schedule_id": "schedule-client",
                "scenario_id": "scenario-client",
                "execution_id": "execution-client",
                "event_id": "auth-1",
                "event_type": "authorization",
                "scheduled_for": scheduled_for.isoformat(),
                "idempotency_key": "schedule-client:auth-1",
                "payload": {"amount_cents": 4200},
            }
        )
        listed = await client.list_events(schedule_id="schedule-client")
    finally:
        Base.metadata.drop_all(bind=engine)

    assert created.schedule_id == "schedule-client"
    assert listed["count"] == 1
    assert listed["events"][0]["event_id"] == "auth-1"
