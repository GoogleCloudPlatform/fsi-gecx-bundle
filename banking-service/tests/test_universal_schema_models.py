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
import models.identity as identity_models
import models.origination as orig_models


@pytest.fixture(scope="function")
def test_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    
    @event.listens_for(engine, "connect")
    def attach_sqlite_schemas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("ATTACH DATABASE 'file:identity_test?mode=memory&cache=shared' AS identity;")
        cursor.execute("ATTACH DATABASE 'file:kyc_test?mode=memory&cache=shared' AS kyc;")
        cursor.execute("ATTACH DATABASE 'file:ledger_test?mode=memory&cache=shared' AS ledger;")
        cursor.close()

    # Create all tables across attached schemas
    Base.metadata.create_all(bind=engine)
    
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def test_identity_models_creation(test_db):
    user = identity_models.User(
        auth_provider_uid="firebase_user_123",
        first_name="Jane",
        last_name="Doe",
        email="jane.doe@example.com",
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)

    assert user.id is not None
    assert isinstance(user.id, uuid.UUID)
    assert user.auth_provider_uid == "firebase_user_123"

    device = identity_models.UserDevice(
        user_id=user.id,
        device_token="fcm_token_xyz"
    )
    test_db.add(device)
    test_db.commit()
    test_db.refresh(device)
    assert device.user_id == user.id

    msg = identity_models.UserSecureMessage(
        message_id="msg_001",
        user_id=user.id,
        sender="user",
        message="Hello support",
        thread_id="thread_001"
    )
    test_db.add(msg)
    test_db.commit()
    test_db.refresh(msg)
    assert msg.message == "Hello support"


def test_origination_and_ledger_models(test_db):
    user = identity_models.User(
        auth_provider_uid="firebase_user_456",
        first_name="John",
        last_name="Smith",
    )
    test_db.add(user)
    test_db.commit()

    account = orig_models.Account(
        user_id=user.id,
        account_number="CHK-998877",
        account_type="CHECKING",
        product_name="Nova Classic Everyday",
        cleared_balance_cents=50000,
    )
    test_db.add(account)
    test_db.commit()
    test_db.refresh(account)

    assert isinstance(account.id, uuid.UUID)
    assert account.account_type == "CHECKING"

    app = orig_models.Application(
        application_id="APP-EXT-111",
        user_id=user.id,
        product_category="MORTGAGE",
        status="SUBMITTED",
    )
    test_db.add(app)
    test_db.commit()

    mortgage = orig_models.MortgageApplication(
        application_id=app.id,
        property_address="123 Main St",
        estimated_value_cents=45000000,
    )
    test_db.add(mortgage)
    test_db.commit()
    test_db.refresh(app)

    assert app.mortgage_detail.property_address == "123 Main St"

    tx = orig_models.Transaction(
        idempotency_key="IDEMP-TX-101",
        user_id=user.id,
        description="Initial deposit",
    )
    test_db.add(tx)
    test_db.commit()

    entry = orig_models.AccountLedgerEntry(
        transaction_id=tx.id,
        account_id=account.id,
        amount_cents=50000,
        entry_type="CREDIT",
    )
    test_db.add(entry)
    test_db.commit()
    test_db.refresh(tx)

    assert len(tx.ledger_splits) == 1
    assert tx.ledger_splits[0].amount_cents == 50000
