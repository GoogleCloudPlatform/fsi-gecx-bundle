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

"""Credit product catalog contract: read API, origination guard, seed sync and consistency.

Endpoint and origination tests run against test-owned products so lineup
changes in credit_products.json never require touching these assertions.
"""
from decimal import Decimal

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from models.credit_card import CreditProduct
from models.credit_product_catalog import CreditProductSeed
from models.origination import Application
from services import seeding_service
from scripts import database_lifecycle
from services.credit_product_catalog import (
    _insert_ignoring_conflicts,
    load_credit_product_seed,
    sync_credit_product_catalog,
)
from utils.auth import get_current_user
from utils.database import Base, create_db_engine, get_db

CATALOG_PATH = "/api/v1/catalog/credit-products"


@pytest.fixture
def catalog_db():
    engine = create_db_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    def sessions():
        with factory() as db:
            yield db

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = sessions
    try:
        with factory() as db:
            yield db
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _product(code, *, display_order, is_active=True, **terms):
    values = dict(
        product_code=code,
        product_name=f"Test {code}",
        display_order=display_order,
        is_active=is_active,
        tagline="Tagline",
        best_for="Testing",
        min_credit_limit_cents=50000,
        max_credit_limit_cents=2500000,
        purchase_apr=Decimal("0.2249"),
        features=["Feature one"],
    )
    values.update(terms)
    return CreditProduct(**values)


@pytest.fixture
def test_products(catalog_db):
    catalog_db.add_all([
        _product("SECOND", display_order=2),
        _product(
            "FIRST",
            display_order=1,
            intro_purchase_apr=Decimal("0"),
            intro_purchase_apr_months=12,
            cashback_rate=Decimal("0.0150"),
            foreign_transaction_fee_rate=Decimal("0.0300"),
            late_fee_maximum_minor=4000,
        ),
        _product("RETIRED", display_order=0, is_active=False),
    ])
    catalog_db.commit()
    return catalog_db


async def test_lists_only_active_products_in_display_order(client, test_products):
    response = await client.get(CATALOG_PATH)

    assert response.status_code == 200
    assert [p["product_code"] for p in response.json()["products"]] == ["FIRST", "SECOND"]


async def test_v1_alias_serves_the_same_catalog(client, test_products):
    primary = await client.get(CATALOG_PATH)
    alias = await client.get("/v1/catalog/credit-products")

    assert alias.status_code == 200
    assert alias.json() == primary.json()


async def test_money_and_rates_use_repo_presentation_shapes(client, test_products):
    first = (await client.get(CATALOG_PATH)).json()["products"][0]

    assert first["min_credit_limit"] == {
        "money": {"amount_minor": 50000, "currency_code": "USD"},
        "locale": "en-US",
        "display_text": "USD 500.00",
    }
    assert first["late_fee_maximum"]["display_text"] == "USD 40.00"
    assert first["purchase_apr"] == {"rate": "0.2249", "display_text": "22.49%"}
    assert first["foreign_transaction_fee_rate"] == {"rate": "0.0300", "display_text": "3%"}
    assert first["intro_purchase_apr"] == {
        "apr": {"rate": "0.0000", "display_text": "0%"},
        "months": 12,
        "display_text": "0% intro APR for 12 months",
    }
    assert first["intro_balance_transfer_apr"] is None
    assert first["penalty_apr"] is None
    assert first["rewards"]["type"] == "CASHBACK"
    assert first["rewards"]["display_text"] == "1.5% cash back on all purchases"


async def test_catalog_is_public_while_protected_routes_refuse(client, test_products):
    def refuse():
        raise HTTPException(status_code=401, detail="Invalid token")

    app.dependency_overrides[get_current_user] = refuse
    catalog = await client.get(CATALOG_PATH)
    protected = await client.post(
        "/applications",
        json={"product_category": "CARD", "product_type": "FIRST"},
    )

    assert catalog.status_code == 200
    assert protected.status_code == 401


async def test_card_application_accepts_active_catalog_code(client, test_products):
    response = await client.post(
        "/applications",
        json={"product_category": "CARD", "product_type": "FIRST", "requested_amount": 5000.0},
    )

    assert response.status_code == 200
    application = test_products.query(Application).filter_by(
        application_id=response.json()["application_id"]
    ).one()
    assert application.credit_card_detail.card_product_id == "FIRST"


@pytest.mark.parametrize(
    "product_type",
    ["NOT_A_PRODUCT", "RETIRED", "AURA_ELITE_RESERVE", "RESIDENTIAL_MORTGAGE"],
)
async def test_card_application_rejects_codes_that_are_not_active_products(
    client, test_products, product_type
):
    response = await client.post(
        "/applications",
        json={"product_category": "CREDIT_CARD", "product_type": product_type},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "UNKNOWN_CREDIT_PRODUCT"
    assert test_products.query(Application).count() == 0


async def test_loan_application_rejects_card_codes(client, test_products):
    response = await client.post(
        "/applications",
        json={"product_category": "LOAN", "product_type": "FIRST"},
    )

    assert response.status_code == 422
    assert test_products.query(Application).count() == 0


def test_sync_seeds_empty_catalog_from_json(catalog_db):
    sync_credit_product_catalog(catalog_db)

    codes = {p.product_code for p in catalog_db.query(CreditProduct)}
    assert codes == {row.product_code for row in load_credit_product_seed()}


def test_sync_refreshes_stale_terms_and_is_idempotent(catalog_db):
    seed = load_credit_product_seed()
    target = seed[0]
    catalog_db.add(_product(
        target.product_code, display_order=99, is_active=False, purchase_apr=Decimal("0.9999")
    ))
    catalog_db.commit()

    sync_credit_product_catalog(catalog_db)
    catalog_db.commit()
    refreshed = catalog_db.get(CreditProduct, target.product_code)
    assert refreshed.product_name == target.product_name
    assert Decimal(str(refreshed.purchase_apr)) == target.purchase_apr
    assert refreshed.is_active is target.is_active
    assert refreshed.features == target.features

    writes = _count_writes(catalog_db)
    sync_credit_product_catalog(catalog_db)
    assert writes == []


def _count_writes(db):
    writes = []
    event.listen(
        db.get_bind(), "before_cursor_execute",
        lambda conn, cursor, statement, *args: writes.append(statement)
        if statement.lstrip().upper().startswith(("UPDATE", "INSERT")) else None,
    )
    return writes


async def test_sync_deactivates_products_missing_from_seed(client, catalog_db):
    catalog_db.add(_product("DISCONTINUED_CARD", display_order=0))
    catalog_db.commit()

    sync_credit_product_catalog(catalog_db)
    catalog_db.commit()

    assert catalog_db.get(CreditProduct, "DISCONTINUED_CARD").is_active is False
    listed = [p["product_code"] for p in (await client.get(CATALOG_PATH)).json()["products"]]
    assert "DISCONTINUED_CARD" not in listed
    writes = _count_writes(catalog_db)
    sync_credit_product_catalog(catalog_db)
    assert writes == []


def test_sync_refreshes_row_left_with_migration_defaults(catalog_db):
    target = load_credit_product_seed()[0]
    catalog_db.add(CreditProduct(
        product_code=target.product_code,
        product_name="Legacy name",
        min_credit_limit_cents=1,
        max_credit_limit_cents=2,
        purchase_apr=Decimal("0.1"),
    ))
    catalog_db.commit()
    stale = catalog_db.get(CreditProduct, target.product_code)
    assert (stale.tagline, stale.features, stale.late_fee_maximum_minor) == ("", [], 0)

    sync_credit_product_catalog(catalog_db)
    catalog_db.commit()

    assert stale.tagline == target.tagline
    assert stale.features == target.features
    assert stale.late_fee_maximum_minor == target.late_fee_maximum_minor
    assert stale.max_credit_limit_cents == target.max_credit_limit_cents


def test_insert_tolerates_a_row_created_concurrently(catalog_db):
    target = load_credit_product_seed()[0]
    catalog_db.add(_product(target.product_code, display_order=99, product_name="Concurrent writer"))
    catalog_db.commit()

    _insert_ignoring_conflicts(catalog_db, [target.model_dump()])
    sync_credit_product_catalog(catalog_db)
    catalog_db.commit()

    assert catalog_db.get(CreditProduct, target.product_code).product_name == target.product_name


def test_reconcile_syncs_catalog_after_verifying_schema_head(monkeypatch):
    calls = []
    for step in ("reconcile_ownership", "reconcile_grants", "reconcile_cdc", "ensure_replication_slot"):
        monkeypatch.setattr(database_lifecycle, step, lambda *a, **k: None)
    monkeypatch.setattr(
        database_lifecycle, "verify",
        lambda *a, **k: calls.append("verify") or {"phase": "reconcile", "status": "ok"},
    )
    monkeypatch.setattr(database_lifecycle, "sync_reference_catalogs", lambda engine: calls.append("sync"))
    engine = create_db_engine("sqlite:///:memory:", poolclass=StaticPool)

    result = database_lifecycle.reconcile(engine, _lifecycle_config())

    assert calls == ["verify", "sync"]
    assert result["reference_catalogs"] == "synced"


def test_reference_catalog_sync_commits_seed_lineup():
    engine = create_db_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)

    database_lifecycle.sync_reference_catalogs(engine)

    with sessionmaker(bind=engine)() as db:
        codes = {p.product_code for p in db.query(CreditProduct).filter_by(is_active=True)}
    assert codes == {row.product_code for row in load_credit_product_seed() if row.is_active}
    engine.dispose()


def _lifecycle_config():
    return database_lifecycle.LifecycleConfig(
        project_id="example-project",
        target_database="banking",
        migration_user="migration@example-project.iam",
        cdc_user="banking_bq_connector",
        create_missing_principals=False,
        reconcile_cdc=False,
        expected_revision=None,
        support_users=(),
        viewer_users=(),
    )


@pytest.mark.parametrize(
    "change",
    [
        {"min_credit_limit_cents": 3000000, "max_credit_limit_cents": 1000000},
        {"intro_purchase_apr": "0.0000", "intro_purchase_apr_months": None},
        {"cashback_rate": "0.0150", "travel_multiplier": 3},
        {"purchase_apr": "1.5000"},
        {"currency_code": "EUR"},
    ],
    ids=["limit-bounds", "intro-without-months", "cashback-and-points", "rate-over-100pct", "currency"],
)
def test_seed_validation_rejects_incoherent_terms(change):
    row = load_credit_product_seed()[0].model_dump(mode="json")
    row.update(change)

    with pytest.raises(ValidationError):
        CreditProductSeed.model_validate(row)


INVALID_STORED_TERMS = {
    "intro-apr-without-months": {"intro_purchase_apr": Decimal("0"), "intro_purchase_apr_months": None},
    "intro-months-without-apr": {"intro_balance_transfer_apr_months": 12},
    "rate-over-100pct": {"penalty_apr": Decimal("1.5")},
    "negative-fee": {"late_fee_maximum_minor": -1},
    "unsupported-currency": {"currency_code": "EUR"},
}


@pytest.mark.parametrize("terms", INVALID_STORED_TERMS.values(), ids=INVALID_STORED_TERMS.keys())
def test_database_rejects_incoherent_stored_terms(catalog_db, terms):
    catalog_db.add(_product("BROKEN", display_order=1, **terms))

    with pytest.raises(IntegrityError):
        catalog_db.commit()


def test_every_seeded_credit_account_uses_an_active_product_within_its_limits():
    products = {p.product_code: p for p in load_credit_product_seed() if p.is_active}
    holdings = [
        (persona["email"], persona["credit_product"], persona["credit_limit_cents"])
        for persona in seeding_service.get_seeding_personas()
    ]
    baseline = seeding_service.PRESENTER_CREDIT_BASELINE
    holdings.append(("presenter-default", baseline["credit_product"], baseline["credit_limit"]))

    assert seeding_service.DEFAULT_SEEDED_CREDIT_PRODUCT in products
    for who, code, limit in holdings:
        assert code in products, f"{who} holds unknown or inactive product {code}"
        product = products[code]
        assert product.min_credit_limit_cents <= limit <= product.max_credit_limit_cents, (
            f"{who} limit {limit} outside {code} bounds"
        )
