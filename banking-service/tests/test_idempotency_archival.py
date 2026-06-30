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
import datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.origination import Transaction, Base
from utils.idempotency import archive_stale_transactions


@pytest.fixture
def tx_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_archive_stale_transactions(tx_db):
    user_id = uuid.uuid4()
    now = datetime.datetime.now(datetime.timezone.utc)
    old_time = now - datetime.timedelta(days=40)
    recent_time = now - datetime.timedelta(days=10)

    tx_old = Transaction(
        id=uuid.uuid4(),
        idempotency_key="key_old_1",
        user_id=user_id,
        status="COMPLETED",
        description="Old transaction",
        request_hash="hash_old",
        response_payload='{"status": "success", "data": "large_payload_old"}',
        created_at=old_time
    )
    tx_recent = Transaction(
        id=uuid.uuid4(),
        idempotency_key="key_recent_1",
        user_id=user_id,
        status="COMPLETED",
        description="Recent transaction",
        request_hash="hash_recent",
        response_payload='{"status": "success", "data": "large_payload_recent"}',
        created_at=recent_time
    )
    tx_db.add(tx_old)
    tx_db.add(tx_recent)
    tx_db.commit()

    archived_count = archive_stale_transactions(tx_db, retention_days=30)
    assert archived_count == 1

    updated_old = tx_db.query(Transaction).filter_by(idempotency_key="key_old_1").first()
    assert updated_old.response_payload is None
    assert updated_old.request_hash == "ARCHIVED_EXPIRED"

    updated_recent = tx_db.query(Transaction).filter_by(idempotency_key="key_recent_1").first()
    assert updated_recent.response_payload is not None
