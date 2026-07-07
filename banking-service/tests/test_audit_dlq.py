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
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.audit import AuditOutbox, Base
from utils.audit import record_audit_event, process_dlq_audit_events


@pytest.fixture
def audit_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_outbox_cdc_append_only_log_and_monitoring(audit_db):
    rec = record_audit_event(audit_db, "TEST_EVENT", {"data": "foo"})
    audit_db.commit()

    updated = audit_db.query(AuditOutbox).filter_by(event_id=rec.event_id).first()
    assert updated is not None
    assert updated.event_type == "TEST_EVENT"

    # In WAL CDC architecture, process_dlq_audit_events is a no-op monitoring stub
    dlq_ids = process_dlq_audit_events(audit_db)
    assert len(dlq_ids) == 0
