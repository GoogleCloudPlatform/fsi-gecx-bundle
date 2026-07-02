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
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from utils.database import Base
from services.seeding_service import perform_algorithmic_seeding
from models.identity import User, UserAddress
from models.kyc import KYCRecord, UserCreditProfile
from models.origination import Account
from models.credit_card import CreditAccount, IssuedCard
from models.settings import SystemSetting

DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture(name="db_session")
def fixture_db_session():
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # Initialize all database tables
    Base.metadata.create_all(bind=engine)
    
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

def test_perform_algorithmic_seeding_success(db_session):
    # Execute seeding
    manifest = perform_algorithmic_seeding(db_session)
    
    # Assert manifest is returned and contains baseline personas
    assert len(manifest) >= 19
    assert "marcus" in manifest
    assert "chloe" in manifest
    assert "david" in manifest
    assert "jane" in manifest
    assert "larry" in manifest
    
    # Assert database table counts for multi-metro and VIP population
    assert db_session.query(User).count() >= 19
    assert db_session.query(UserAddress).count() >= 19
    assert db_session.query(KYCRecord).count() >= 19
    assert db_session.query(UserCreditProfile).count() >= 19
    assert db_session.query(Account).count() >= 36
    assert db_session.query(CreditAccount).count() >= 19
    assert db_session.query(IssuedCard).count() >= 19
    
    # Assert SystemSetting contains the manifest
    setting = db_session.query(SystemSetting).filter(SystemSetting.key == "simulation_cards_manifest").first()
    assert setting is not None
    loaded_manifest = json.loads(setting.value)
    assert loaded_manifest["marcus"]["cardholder_name"] == "Marcus Vance"
    assert loaded_manifest["jane"]["token"] == "tok_visa_jane_doe"
