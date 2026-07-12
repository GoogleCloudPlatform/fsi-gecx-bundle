from fastapi.testclient import TestClient

from main import app
from models.authentication import ValidatedToken
from routers import internal
from routers.internal import RESET_DATA_LAKE_TABLES
from utils.auth import get_current_user


client = TestClient(app)


def _override_user(email: str):
    def current_user():
        return ValidatedToken(claims={"sub": "reset-operator", "email": email})

    return current_user


def test_full_reset_access_defaults_to_disabled(monkeypatch):
    monkeypatch.delenv("FULL_RESET_ENABLED", raising=False)
    monkeypatch.delenv("FULL_RESET_OPERATOR_EMAILS", raising=False)
    monkeypatch.delenv("DATABASE_IAM_SUPPORT_USERS", raising=False)
    app.dependency_overrides[get_current_user] = _override_user("admin@google.com")
    try:
        access = client.get("/internal/debug/reset-db/access")
        blocked = client.post("/internal/debug/reset-db")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert access.status_code == 200
    assert access.json()["allowed"] is False
    assert access.json()["reason"] == "FULL_RESET_DISABLED"
    assert blocked.status_code == 403
    assert "personal demo reset" in blocked.json()["detail"]


def test_full_reset_access_respects_operator_allowlist(monkeypatch):
    monkeypatch.setenv("FULL_RESET_ENABLED", "true")
    monkeypatch.setenv("FULL_RESET_OPERATOR_EMAILS", "owner@example.com,reset-admin@google.com")
    monkeypatch.delenv("DATABASE_IAM_SUPPORT_USERS", raising=False)
    app.dependency_overrides[get_current_user] = _override_user("reset-admin@google.com")
    try:
        response = client.get("/internal/debug/reset-db/access")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    data = response.json()
    assert data["allowed"] is True
    assert data["operator_allowlist_configured"] is True
    assert data["reason"] == "ALLOWED"


def test_full_reset_access_blocks_non_allowlisted_operator(monkeypatch):
    monkeypatch.setenv("FULL_RESET_ENABLED", "true")
    monkeypatch.setenv("FULL_RESET_OPERATOR_EMAILS", "owner@example.com")
    monkeypatch.delenv("DATABASE_IAM_SUPPORT_USERS", raising=False)
    app.dependency_overrides[get_current_user] = _override_user("admin@google.com")
    try:
        response = client.get("/internal/debug/reset-db/access")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert response.json()["allowed"] is False
    assert response.json()["reason"] == "OPERATOR_NOT_ALLOWLISTED"


def test_full_reset_access_respects_database_iam_support_users(monkeypatch):
    monkeypatch.setenv("FULL_RESET_ENABLED", "true")
    monkeypatch.delenv("FULL_RESET_OPERATOR_EMAILS", raising=False)
    monkeypatch.setenv(
        "DATABASE_IAM_SUPPORT_USERS",
        "group:fsi-nova-horizon-dba-external@google.com,user:reset-admin@google.com",
    )
    app.dependency_overrides[get_current_user] = _override_user("reset-admin@google.com")
    try:
        response = client.get("/internal/debug/reset-db/access")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    data = response.json()
    assert data["allowed"] is True
    assert data["operator_allowlist_configured"] is True
    assert data["reason"] == "ALLOWED"


def test_full_reset_access_does_not_treat_group_principal_as_membership_claim(monkeypatch):
    monkeypatch.setenv("FULL_RESET_ENABLED", "true")
    monkeypatch.delenv("FULL_RESET_OPERATOR_EMAILS", raising=False)
    monkeypatch.setenv("DATABASE_IAM_SUPPORT_USERS", "group:fsi-nova-horizon-dba-external@google.com")
    app.dependency_overrides[get_current_user] = _override_user("reset-admin@google.com")
    try:
        response = client.get("/internal/debug/reset-db/access")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert response.json()["allowed"] is False
    assert response.json()["reason"] == "OPERATOR_NOT_ALLOWLISTED"


def test_full_reset_data_lake_purge_covers_ledger_and_merchant_cdc_tables():
    assert {
        "catalog_credit_products",
        "catalog_deposit_products",
        "cards_credit_accounts",
        "cards_issued_card",
        "cards_posted_transactions",
        "cards_transaction_authorization",
        "identity_user_addresses",
        "identity_user_devices",
        "identity_user_secure_messages",
        "identity_users",
        "kyc_user_credit_profiles",
        "ledger_account_ledger",
        "ledger_accounts",
        "ledger_transactions",
        "merchants_merchant_category_codes",
        "merchants_merchant_master",
        "merchants_merchant_stores",
        "operations_fraud_alerts",
        "operations_fraud_case_actions",
        "operations_fraud_model_decisions",
        "operations_retail_locations",
        "operations_scenario_outcomes",
        "operations_support_escalations",
        "origination_application_artifacts",
        "origination_deposit_applications",
    }.issubset(RESET_DATA_LAKE_TABLES)


def test_full_reset_data_lake_purge_uses_schema_prefixed_cdc_table_names():
    assert {
        "credit_products",
        "deposit_products",
        "kyc_records",
        "user_credit_profiles",
    }.isdisjoint(RESET_DATA_LAKE_TABLES)


def test_full_reset_data_lake_purge_uses_truncate(monkeypatch):
    class FakeTableRow:
        def __init__(self, table_name):
            self.table_name = table_name

    class FakeQueryResult:
        def __init__(self, rows=()):
            self._rows = rows

        def result(self):
            return self._rows

    class FakeBigQueryClient:
        def __init__(self):
            self.queries = []

        def query(self, sql):
            self.queries.append(sql)
            if "INFORMATION_SCHEMA.TABLES" in sql:
                return FakeQueryResult(
                    [
                        FakeTableRow("cards_transaction_authorization"),
                        FakeTableRow("merchants_merchant_master"),
                    ]
                )
            return FakeQueryResult()

    fake_client = FakeBigQueryClient()
    monkeypatch.setattr(internal.bq_client, "query", fake_client.query)

    purged = internal._purge_data_lake_tables("demo-project")

    assert purged == ["cards_transaction_authorization", "merchants_merchant_master"]
    assert "TRUNCATE TABLE `demo-project.iceberg_catalog.cards_transaction_authorization`" in fake_client.queries
    assert "TRUNCATE TABLE `demo-project.iceberg_catalog.merchants_merchant_master`" in fake_client.queries
    assert all("DELETE FROM" not in query for query in fake_client.queries)
