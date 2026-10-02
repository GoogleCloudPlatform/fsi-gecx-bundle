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

import datetime
import json
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.audit import AuditOutbox, OutboxRelayCheckpoint
from scripts.audit_outbox_relay import AuditOutboxRelay


@pytest.fixture
def relay_db():
    engine = create_engine("sqlite:///:memory:", execution_options={"schema_translate_map": {schema: None for schema in ("identity", "kyc", "ledger", "cards", "operations", "origination", "audit", "admin", "catalog", "ref_data")}})
    AuditOutbox.__table__.create(engine)
    OutboxRelayCheckpoint.__table__.create(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        OutboxRelayCheckpoint.__table__.drop(engine)
        AuditOutbox.__table__.drop(engine)
        engine.dispose()


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


def test_relay_preserves_nonfinancial_proposal_contract_version_and_identity(relay_db):
    relay_db.add(AuditOutbox(event_id="proposal-event", event_type="ACTION_PROPOSAL_CONFIRMED", schema_version=2,
        payload='{"audit_contract":"proposal-audit.v2","proposal_id":"pinned-proposal"}'))
    relay_db.commit()
    publisher = _publisher()
    result = AuditOutboxRelay(relay_db, publisher, "projects/p/topics/audit").run()
    message = json.loads(publisher.publish.call_args.args[1])
    assert result.published == 1
    assert message["event_id"] == "proposal-event"
    assert message["schema_version"] == 2
    assert json.loads(message["payload"])["proposal_id"] == "pinned-proposal"
