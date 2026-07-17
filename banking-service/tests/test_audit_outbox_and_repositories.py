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

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from utils.database import Base
from models.audit import AuditOutbox, OutboxRelayCheckpoint
from utils.audit import record_audit_event


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
            "ATTACH DATABASE 'file:audit_repo?mode=memory&cache=shared' AS audit;",
            "ATTACH DATABASE 'file:admin_repo?mode=memory&cache=shared' AS admin;",
            "ATTACH DATABASE 'file:catalog_repo?mode=memory&cache=shared' AS catalog;",
            "ATTACH DATABASE 'file:ref_data_repo?mode=memory&cache=shared' AS ref_data;",
        ]:
            try:
                cursor.execute(stmt)
            except Exception:
                pass
        cursor.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.query(AuditOutbox).delete()
    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def test_outbox_commit_and_append_only_invariance(test_db):
    entry = record_audit_event(test_db, "USER_CREATED", {"user_id": "usr_123", "email": "test@example.com"})
    assert entry.event_type == "USER_CREATED"
    assert entry.created_at is not None
    test_db.commit()

    all_events = test_db.query(AuditOutbox).all()
    assert len(all_events) == 1
    assert all_events[0].event_id == entry.event_id


def test_outbox_transaction_rollback_invariance(test_db):
    try:
        record_audit_event(test_db, "APPLICATION_SUBMITTED", {"app_id": "app_999"})
        # Simulate database error causing rollback
        raise ValueError("Simulated constraint failure")
    except ValueError:
        test_db.rollback()

    all_records = test_db.query(AuditOutbox).all()
    assert len(all_records) == 0


def test_outbox_cdc_monitoring_and_pruning(test_db):
    import datetime
    from utils.audit import prune_historical_audit_events
    entry = record_audit_event(test_db, "DEVICE_REGISTERED", {"device_token": "token_abc"})
    entry.created_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=45)
    test_db.commit()

    # Unrelayed source rows are protected regardless of age.
    deleted = prune_historical_audit_events(test_db, retention_days=30)
    assert deleted == 0

    test_db.add(
        OutboxRelayCheckpoint(
            relay_name="audit-events-v1",
            last_created_at=datetime.datetime.now(datetime.timezone.utc),
            last_event_id=entry.event_id,
            published_count=1,
        )
    )
    test_db.commit()
    deleted = prune_historical_audit_events(test_db, retention_days=30)
    assert deleted == 1
    assert test_db.query(AuditOutbox).count() == 0
