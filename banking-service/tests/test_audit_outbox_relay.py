import datetime
import json
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.audit import AuditOutbox, OutboxRelayCheckpoint
from scripts.audit_outbox_relay import AuditOutboxRelay
from utils.database import Base


@pytest.fixture
def relay_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def _publisher():
    publisher = MagicMock()
    publisher.publish.return_value.result.return_value = "message-id"
    return publisher


def test_relay_publishes_in_cursor_order_and_advances_checkpoint(relay_db):
    timestamp = datetime.datetime(2026, 7, 16, 12, 0, tzinfo=datetime.timezone.utc)
    relay_db.add_all([
        AuditOutbox(event_id="b", event_type="SECOND", payload='{"value":2}', created_at=timestamp),
        AuditOutbox(event_id="a", event_type="FIRST", payload='{"value":1}', created_at=timestamp),
    ])
    relay_db.commit()
    publisher = _publisher()

    result = AuditOutboxRelay(relay_db, publisher, "projects/p/topics/audit").run(batch_size=10)

    assert result.published == 2
    messages = [json.loads(call.args[1]) for call in publisher.publish.call_args_list]
    assert [message["event_id"] for message in messages] == ["a", "b"]
    assert messages[0]["payload"] == '{"value":1}'
    checkpoint = relay_db.get(OutboxRelayCheckpoint, "audit-events-v1")
    assert checkpoint.last_event_id == "b"
    assert checkpoint.published_count == 2

    replay = AuditOutboxRelay(relay_db, publisher, "projects/p/topics/audit").run(batch_size=10)
    assert replay.published == 0
    assert publisher.publish.call_count == 2


def test_publish_failure_rolls_back_cursor_for_at_least_once_retry(relay_db):
    relay_db.add(AuditOutbox(event_id="event-1", event_type="TEST", payload="{}"))
    relay_db.commit()
    publisher = _publisher()
    publisher.publish.return_value.result.side_effect = RuntimeError("publish failed")

    with pytest.raises(RuntimeError, match="publish failed"):
        AuditOutboxRelay(relay_db, publisher, "projects/p/topics/audit").run()

    assert relay_db.get(OutboxRelayCheckpoint, "audit-events-v1") is None


def test_dry_run_neither_publishes_nor_advances(relay_db):
    relay_db.add(AuditOutbox(event_id="event-1", event_type="TEST", payload="{}"))
    relay_db.commit()
    publisher = _publisher()

    result = AuditOutboxRelay(relay_db, publisher, "projects/p/topics/audit").run(dry_run=True)

    assert result.status == "dry_run"
    assert result.published == 1
    publisher.publish.assert_not_called()
    assert relay_db.get(OutboxRelayCheckpoint, "audit-events-v1") is None
