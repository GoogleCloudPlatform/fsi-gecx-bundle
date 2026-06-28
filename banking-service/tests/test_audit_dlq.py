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

import uuid
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.audit import AuditOutbox, Base
from utils.audit import record_audit_event, publish_pending_audit_events, process_dlq_audit_events, MAX_RETRIES


@pytest.fixture
def audit_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@patch("utils.audit.get_publisher_client")
def test_outbox_publish_failure_to_dlq(mock_get_pub, audit_db, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-proj")
    monkeypatch.setenv("PUBSUB_TOPIC_AUDIT", "test-topic")

    mock_pub = MagicMock()
    mock_pub.topic_path.return_value = "projects/test-proj/topics/test-topic"
    mock_pub.publish.side_effect = Exception("PubSub Network Timeout")
    mock_get_pub.return_value = mock_pub

    rec = record_audit_event(audit_db, "TEST_EVENT", {"data": "foo"})
    audit_db.commit()

    # Trigger publish multiple times until max retries reached
    for _ in range(MAX_RETRIES):
        publish_pending_audit_events(audit_db)

    updated = audit_db.query(AuditOutbox).filter_by(event_id=rec.event_id).first()
    assert updated.status == "DLQ"
    assert updated.retry_count == MAX_RETRIES

    dlq_ids = process_dlq_audit_events(audit_db)
    assert rec.event_id in dlq_ids
