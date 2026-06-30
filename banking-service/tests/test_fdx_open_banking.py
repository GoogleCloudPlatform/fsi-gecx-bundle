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
from fastapi.testclient import TestClient
from main import app
from models.authentication import ValidatedToken
from utils.auth import get_current_user
from utils.database import SessionLocal
from services.credit_card import initialize_db_and_seed

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    db = SessionLocal()
    try:
        initialize_db_and_seed(db)
    finally:
        db.close()


def test_taxonomy_service():
    from services.taxonomy_service import TaxonomyService
    cat = TaxonomyService.get_category("5411")
    assert cat.primary == "GENERAL_MERCHANDISE"
    assert cat.detailed == "GENERAL_MERCHANDISE_SUPERSTORES"
    
    # Test fallback
    cat_unknown = TaxonomyService.get_category("9999")
    assert cat_unknown.primary == "GENERAL_MERCHANDISE"


def test_fdx_account_info_unauthorized_scope():
    app.dependency_overrides[get_current_user] = lambda: ValidatedToken(claims={"sub": "cust-123", "scope": "other:scope"})
    try:
        resp = client.get("/api/fdx/v6/accounts/88888888-8888-4888-8888-999999999999")
        assert resp.status_code == 403
        assert "Insufficient scope" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_fdx_account_info_success():
    app.dependency_overrides[get_current_user] = lambda: ValidatedToken(claims={"sub": "cust-123", "scope": "accounts:read"})
    try:
        resp = client.get("/api/fdx/v6/accounts/88888888-8888-4888-8888-999999999999")
        assert resp.status_code == 200
        data = resp.json()
        assert data["account_id"] == "88888888-8888-4888-8888-999999999999"
        assert data["account_number_display"] == "8234"  # Masked PAN
        assert data["iso_currency_code"] == "USD"
    finally:
        app.dependency_overrides.clear()


def test_fdx_idor_prevention():
    # Attempting to read cust-123's account using cust-999 token
    app.dependency_overrides[get_current_user] = lambda: ValidatedToken(claims={"sub": "cust-999", "scope": "accounts:read"})
    try:
        resp = client.get("/api/fdx/v6/accounts/88888888-8888-4888-8888-999999999999")
        assert resp.status_code == 403
        assert "Account not found or access denied" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_realtime_balance_success():
    app.dependency_overrides[get_current_user] = lambda: ValidatedToken(claims={"sub": "cust-123", "scope": "accounts:read"})
    try:
        resp = client.get("/api/fdx/v6/accounts/88888888-8888-4888-8888-999999999999/balance/realtime")
        assert resp.status_code == 200
        data = resp.json()
        assert "realtime_available_credit" in data
        assert data["iso_currency_code"] == "USD"
    finally:
        app.dependency_overrides.clear()


def test_unified_transactions_success():
    app.dependency_overrides[get_current_user] = lambda: ValidatedToken(claims={"sub": "cust-123", "scope": "transactions:read"})
    try:
        resp = client.get("/api/fdx/v6/accounts/88888888-8888-4888-8888-999999999999/transactions")
        assert resp.status_code == 200
        data = resp.json()
        assert "transactions" in data
        assert "total" in data
    finally:
        app.dependency_overrides.clear()


def test_payment_networks_success():
    app.dependency_overrides[get_current_user] = lambda: ValidatedToken(claims={"sub": "cust-123", "scope": "accounts:read"})
    try:
        resp = client.get("/api/fdx/v6/accounts/88888888-8888-4888-8888-999999999999/payment-networks")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["payment_networks"]) == 1
        assert data["payment_networks"][0]["type"] == "US_ACH"
        assert data["payment_networks"][0]["transfer_in"] is True
    finally:
        app.dependency_overrides.clear()


def test_list_taxonomies_success():
    app.dependency_overrides[get_current_user] = lambda: ValidatedToken(claims={"sub": "cust-123", "scope": "accounts:read"})
    try:
        resp = client.get("/api/fdx/v6/taxonomies")
        assert resp.status_code == 200
        data = resp.json()
        assert "5411" in data
        assert data["5411"]["primary"] == "GENERAL_MERCHANDISE"
    finally:
        app.dependency_overrides.clear()


def test_get_taxonomy_by_mcc_success():
    app.dependency_overrides[get_current_user] = lambda: ValidatedToken(claims={"sub": "cust-123", "scope": "accounts:read"})
    try:
        resp = client.get("/api/fdx/v6/taxonomies/5814")
        assert resp.status_code == 200
        data = resp.json()
        assert data["primary"] == "FOOD_AND_DRINK"
        assert data["detailed"] == "FOOD_AND_DRINK_FAST_FOOD"
    finally:
        app.dependency_overrides.clear()


def test_internal_list_taxonomies_success():
    app.dependency_overrides[get_current_user] = lambda: ValidatedToken(claims={"sub": "cust-123"})
    try:
        resp = client.get("/credit-card/taxonomies")
        assert resp.status_code == 200
        data = resp.json()
        assert "5411" in data
    finally:
        app.dependency_overrides.clear()


def test_internal_get_taxonomy_by_mcc_success():
    app.dependency_overrides[get_current_user] = lambda: ValidatedToken(claims={"sub": "cust-123"})
    try:
        resp = client.get("/credit-card/taxonomies/5814")
        assert resp.status_code == 200
        data = resp.json()
        assert data["primary"] == "FOOD_AND_DRINK"
    finally:
        app.dependency_overrides.clear()
