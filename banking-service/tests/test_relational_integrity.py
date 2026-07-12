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
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from utils.database import Base
from services.seeding_service import perform_algorithmic_seeding, provision_user_suite
from models.identity import User, UserAddress
from models.credit_card import CreditAccount, TransactionAuthorization
from models.merchant import MerchantMaster, MerchantStore
from models.reference import MerchantCategoryCode

DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture(name="db_session")
def fixture_db_session():
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

def test_3nf_relational_join_integrity(db_session):
    # Seed background accounts
    perform_algorithmic_seeding(db_session)
    
    # Provision a presenter demo suite to generate historical transactions and holds
    res = provision_user_suite(db_session, "test.presenter@google.com", "uid-test-3nf")
    assert "user_id" in res

    # Verify 3NF relational join across TransactionAuthorization -> CreditAccount -> User -> UserAddress
    query = (
        db_session.query(TransactionAuthorization, CreditAccount, User, UserAddress)
        .join(CreditAccount, TransactionAuthorization.account_id == CreditAccount.id)
        .join(User, CreditAccount.customer_id == User.id)
        .join(UserAddress, User.id == UserAddress.user_id)
        .filter(UserAddress.address_type == "RESIDENTIAL")
    )
    
    results = query.all()
    assert len(results) > 0, "Expected non-zero joined rows across the 3NF credit account hierarchy"
    
    # Verify exact relationship mapping for the first result
    auth, cred_acc, user, addr = results[0]
    assert auth.account_id == cred_acc.id
    assert cred_acc.customer_id == user.id
    assert user.id == addr.user_id
    assert addr.address_type == "RESIDENTIAL"

    merchant_join = (
        db_session.query(MerchantStore, MerchantMaster)
        .join(MerchantMaster, MerchantStore.merchant_id == MerchantMaster.id)
        .all()
    )
    stores = db_session.query(MerchantStore).all()
    masters = db_session.query(MerchantMaster).all()

    assert stores
    assert masters
    assert len(merchant_join) == len(stores)
    assert all(isinstance(store.merchant_id, uuid.UUID) for store in stores)
    assert all(master.merchant_slug for master in masters)
    assert all(store.merchant_id == master.id for store, master in merchant_join)

    mcc = db_session.query(MerchantCategoryCode).filter(MerchantCategoryCode.mcc == "5411").one()
    assert mcc.id == uuid.uuid5(uuid.NAMESPACE_DNS, "merchant-category-code:5411")
    assert mcc.mcc == "5411"
    assert mcc.primary_category
    assert mcc.detailed_category
    assert isinstance(mcc.risk_score, int)
    assert isinstance(mcc.metadata_json, dict)
