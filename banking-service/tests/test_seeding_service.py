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
import services.seeding_service as seeding_service
from services.seeding_service import perform_algorithmic_seeding, provision_user_suite
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


def test_perform_algorithmic_seeding_can_reset_existing_card_data(db_session):
    first_manifest = perform_algorithmic_seeding(db_session)
    second_manifest = perform_algorithmic_seeding(db_session)

    assert len(first_manifest) >= 19
    assert len(second_manifest) >= 19
    assert db_session.query(User).count() >= 19
    assert db_session.query(IssuedCard).count() >= 19


def test_provision_user_suite_generates_unique_card_tokens_for_same_name(db_session):
    first = provision_user_suite(db_session, "erikvoit@google.com", "uid-erik-one")
    second = provision_user_suite(db_session, "erikvoit@gcp.solutions", "uid-erik-two")

    assert first["first_name"] == "Erikvoit"
    assert second["first_name"] == "Erikvoit"
    assert first["card_token"].startswith("tok_visa_")
    assert second["card_token"].startswith("tok_visa_")
    assert first["card_token"] != second["card_token"]


def test_seeding_job_clears_maintenance_on_failure(monkeypatch):
    class FakeSession:
        closed = False

        def close(self):
            self.closed = True

    fake_session = FakeSession()
    maintenance_calls = []

    def fail_seeding(_db):
        raise RuntimeError("seed exploded")

    monkeypatch.setattr(seeding_service, "SessionLocal", lambda: fake_session)
    monkeypatch.setattr(seeding_service, "perform_algorithmic_seeding", fail_seeding)
    monkeypatch.setattr(seeding_service, "disable_maintenance_mode", lambda: maintenance_calls.append("cleared"))

    with pytest.raises(RuntimeError, match="seed exploded"):
        seeding_service.run_algorithmic_seeding_job()

    assert fake_session.closed is True
    assert maintenance_calls == ["cleared"]
