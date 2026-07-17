from unittest.mock import MagicMock

import pytest

from scripts.bootstrap_iceberg_catalog import CatalogBootstrap, reconcile_bigquery_views


def _response(status_code: int, text: str = ""):
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    return response


def test_catalog_bootstrap_creates_two_namespaces_and_tables():
    session = MagicMock()
    session.post.return_value = _response(200)

    result = CatalogBootstrap(
        session,
        project_id="demo-project",
        catalog_id="nova-audit-lakehouse",
        warehouse="gs://warehouse/audit-lakehouse",
    ).run()

    assert set(result) == {
        "compliance_audit_namespace",
        "financial_ledger_namespace",
        "audit_events_table",
        "account_ledger_entries_table",
    }
    assert session.post.call_count == 4
    audit_table_request = session.post.call_args_list[2]
    assert audit_table_request.kwargs["json"]["properties"]["format-version"] == "2"
    assert audit_table_request.kwargs["json"]["schema"]["fields"][0]["name"] == "event_id"
    assert audit_table_request.kwargs["headers"]["X-Iceberg-Access-Delegation"] == "vended-credentials"


def test_catalog_bootstrap_treats_conflict_as_idempotent_success():
    session = MagicMock()
    session.post.return_value = _response(409, "already exists")
    result = CatalogBootstrap(
        session,
        project_id="demo-project",
        catalog_id="nova-audit-lakehouse",
        warehouse="gs://warehouse/audit-lakehouse",
    ).run()
    assert set(result.values()) == {"exists"}


def test_catalog_bootstrap_surfaces_api_errors():
    session = MagicMock()
    session.post.return_value = _response(403, "permission denied")
    bootstrap = CatalogBootstrap(
        session,
        project_id="demo-project",
        catalog_id="nova-audit-lakehouse",
        warehouse="gs://warehouse/audit-lakehouse",
    )
    with pytest.raises(RuntimeError, match="permission denied"):
        bootstrap.run()


def test_bigquery_views_are_reconciled_after_catalog_tables():
    client = MagicMock()
    names = reconcile_bigquery_views(
        client,
        project_id="demo-project",
        catalog_id="nova-audit-lakehouse",
    )
    assert names == [
        "audit_events",
        "account_ledger_entries",
        "account_ledger_balance",
        "origination_audit_log",
        "financial_ledger_audit_log",
        "identity_access_audit_log",
        "system_config_audit_log",
    ]
    assert client.query.call_count == 7
    audit_query = client.query.call_args_list[0].args[0]
    assert "demo-project.nova-audit-lakehouse.compliance_audit.audit_events" in audit_query
    assert "PARTITION BY event_id" in audit_query
