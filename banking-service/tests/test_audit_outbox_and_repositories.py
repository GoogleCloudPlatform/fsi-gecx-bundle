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
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from utils.database import Base
from models.audit import AuditOutbox
from utils.audit import record_audit_event, publish_pending_audit_events


@pytest.fixture(scope="function")
def test_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    
    @event.listens_for(engine, "connect")
    def attach_sqlite_schemas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        for stmt in [
            "ATTACH DATABASE 'file:identity_repo?mode=memory&cache=shared' AS identity;",
            "ATTACH DATABASE 'file:kyc_repo?mode=memory&cache=shared' AS kyc;",
            "ATTACH DATABASE 'file:ledger_repo?mode=memory&cache=shared' AS ledger;",
            "ATTACH DATABASE 'file:cards_repo?mode=memory&cache=shared' AS cards;",
            "ATTACH DATABASE 'file:operations_repo?mode=memory&cache=shared' AS operations;",
            "ATTACH DATABASE 'file:origination_repo?mode=memory&cache=shared' AS origination;",
        ]:
            try:
                cursor.execute(stmt)
            except Exception:
                pass
        cursor.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def test_outbox_commit_and_publish_success(test_db):
    entry = record_audit_event(test_db, "USER_CREATED", {"user_id": "usr_123", "email": "test@example.com"})
    assert entry.status == "PENDING"
    test_db.commit()

    pending = test_db.query(AuditOutbox).filter(AuditOutbox.status == "PENDING").all()
    assert len(pending) == 1

    # Simulate background publisher running
    count = publish_pending_audit_events(test_db)
    assert count == 1

    published = test_db.query(AuditOutbox).filter(AuditOutbox.status == "PUBLISHED").all()
    assert len(published) == 1
    assert published[0].published_at is not None


def test_outbox_transaction_rollback_invariance(test_db):
    try:
        record_audit_event(test_db, "APPLICATION_SUBMITTED", {"app_id": "app_999"})
        # Simulate database error causing rollback
        raise ValueError("Simulated constraint failure")
    except ValueError:
        test_db.rollback()

    all_records = test_db.query(AuditOutbox).all()
    assert len(all_records) == 0


def test_outbox_dlq_failure_handling(test_db, monkeypatch):
    entry = record_audit_event(test_db, "DEVICE_REGISTERED", {"device_token": "token_abc"})
    test_db.commit()

    # Mock publisher client to raise Exception
    class MockPublisher:
        def topic_path(self, project, topic):
            return f"projects/{project}/topics/{topic}"
        def publish(self, *args, **kwargs):
            raise RuntimeError("Simulated Pub/Sub network failure")

    monkeypatch.setattr("utils.audit.get_publisher_client", lambda: MockPublisher())
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("PUBSUB_TOPIC_AUDIT", "test-topic")

    # Retry up to max retries (5)
    for _ in range(5):
        publish_pending_audit_events(test_db)

    failed_entry = test_db.query(AuditOutbox).filter(AuditOutbox.event_id == entry.event_id).first()
    assert failed_entry.status in ("FAILED", "DLQ")
    assert failed_entry.retry_count == 5
