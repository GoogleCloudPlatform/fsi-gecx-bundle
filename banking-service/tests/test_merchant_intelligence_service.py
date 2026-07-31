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

from services.merchant_intelligence_service import MerchantIntelligenceService
from services.merchant_service import MerchantEnrichmentService
from utils.database import Base


DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(name="db_session")
def fixture_db_session():
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = testing_session_local()
    try:
        yield db
    finally:
        db.close()


def test_merchant_intelligence_matches_alias_and_preserves_risk_as_metadata():
    result = MerchantIntelligenceService.lookup("AMZN Mktplace PMTS 12345", mcc="5311")

    assert result["matched"] is True
    assert result["normalized_merchant"] == "AMAZON"
    assert result["merchant_type"] == "marketplace"
    assert result["merchant_risk_score"] == 45
    assert "CARD_NOT_PRESENT" in result["flags"]
    assert result["mcc_match"] is True


def test_merchant_intelligence_returns_stable_unmatched_shape():
    result = MerchantIntelligenceService.lookup("LOCAL BOOK SHOP 042", mcc="5942")

    assert result == {
        "matched": False,
        "normalized_merchant": "Local Book Shop 042",
        "merchant_type": None,
        "mccs": [],
        "merchant_risk_score": None,
        "flags": [],
        "match_type": None,
        "matched_alias": None,
        "mcc_match": False,
    }


def test_enrichment_uses_intelligence_for_unmatched_descriptor_name_without_risk_override(db_session):
    enriched = MerchantEnrichmentService.enrich_transaction(
        db_session,
        raw_descriptor="DD *DOORDASH 12345",
        mcc="5814",
        country="USA",
    )

    assert enriched["merchant_id"] == "generic-merchant"
    assert enriched["clean_name"] == "DOORDASH"
    assert enriched["risk_score"] == 0
    assert enriched["merchant_intelligence"]["matched"] is True
    assert enriched["merchant_intelligence"]["merchant_risk_score"] > 0
