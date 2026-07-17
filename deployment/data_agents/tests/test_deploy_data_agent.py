import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[1] / "deploy_data_agent.py"
AGENT_SPEC_PATH = Path(__file__).parents[1] / "real_time_analytics_agent.json"
SPEC = importlib.util.spec_from_file_location("deploy_data_agent", MODULE_PATH)
deploy_data_agent = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(deploy_data_agent)


def sample_spec():
    return {
        "agent_id": "real-time-analytics",
        "location": "us",
        "display_name": "Real Time Analytics Agent",
        "description": "Environment-local analytics",
        "system_instruction": "Use local data only.",
        "bigquery_max_billed_bytes": "1024",
        "labels": {"managed-by": "test"},
        "data_sources": [
            {"dataset_id": "analytics_curated", "tables": ["spend_velocity"]},
            {"dataset_id": "compliance_audit", "tables": ["audit_log"]},
        ],
    }


def test_api_endpoint_uses_multi_region_hostname():
    assert (
        deploy_data_agent.api_endpoint("us")
        == "https://geminidataanalytics.us.rep.googleapis.com"
    )
    assert deploy_data_agent.api_endpoint("global") == "https://geminidataanalytics.googleapis.com"
    assert (
        deploy_data_agent.api_endpoint("us-east4")
        == "https://geminidataanalytics-us-east4.googleapis.com"
    )


def test_payload_injects_target_project_and_compliance_sources():
    payload = deploy_data_agent.build_payload(sample_spec(), "fsi-demo-1841")
    context = payload["dataAnalyticsAgent"]["publishedContext"]
    references = context["datasourceReferences"]["bq"]["tableReferences"]

    assert {reference["projectId"] for reference in references} == {"fsi-demo-1841"}
    assert ("compliance_audit", "audit_log") in {
        (reference["datasetId"], reference["tableId"]) for reference in references
    }
    assert context["options"]["datasource"]["bigQueryMaxBilledBytes"] == "1024"
    assert len(payload["labels"]["spec-hash"]) == 16


def test_duplicate_sources_are_rejected():
    spec = sample_spec()
    spec["data_sources"].append(
        {"dataset_id": "analytics_curated", "tables": ["spend_velocity"]}
    )

    with pytest.raises(ValueError, match="Duplicate BigQuery source"):
        deploy_data_agent.expand_table_references(spec, "test-project")


def test_checked_in_spec_uses_reusable_curated_building_blocks():
    spec = deploy_data_agent.load_spec(AGENT_SPEC_PATH)
    references = {
        (reference["datasetId"], reference["tableId"])
        for reference in deploy_data_agent.expand_table_references(spec, "test-project")
    }

    assert ("analytics_curated", "customer_analytics_profiles") in references
    assert ("analytics_curated", "enriched_posted_transactions") in references
    assert ("analytics_curated", "us_customer_metro_distribution") not in references
    assert ("analytics_curated", "customer_cross_border_spend") not in references
    assert ("compliance_audit", "account_ledger_entries") in references
    assert ("compliance_audit", "account_ledger_balance") in references
    assert {
        ("oltp_cdc", "merchants_merchant_category_codes"),
        ("oltp_cdc", "merchants_merchant_master"),
        ("oltp_cdc", "merchants_merchant_stores"),
    } <= references
    assert "evo-genai-workspace" not in AGENT_SPEC_PATH.read_text(encoding="utf-8")


def test_deploy_creates_missing_agent_after_source_validation():
    calls = []

    def requester(url, token, method, payload):
        calls.append((url, method, payload))
        if "/bigquery/v2/" in url:
            return {}
        if method == "GET":
            raise deploy_data_agent.ApiError(404, "not found")
        return payload or {}

    result = deploy_data_agent.deploy(
        "fsi-demo-1841", sample_spec(), "token", requester=requester
    )

    assert result == "created"
    create_call = calls[-1]
    assert create_call[1] == "POST"
    assert "data_agent_id=real-time-analytics" in create_call[0]


def test_check_detects_drift_without_updating():
    def requester(url, token, method, payload):
        if "/bigquery/v2/" in url:
            return {}
        return {"displayName": "Drifted agent"}

    with pytest.raises(RuntimeError, match="has drifted"):
        deploy_data_agent.deploy(
            "evo-genai-workspace",
            sample_spec(),
            "token",
            check_only=True,
            requester=requester,
        )


def test_missing_bigquery_source_blocks_deployment():
    def requester(url, token, method, payload):
        if "compliance_audit" in url:
            raise deploy_data_agent.ApiError(404, "not found")
        return {}

    references = deploy_data_agent.expand_table_references(sample_spec(), "test-project")
    with pytest.raises(RuntimeError, match="compliance_audit.audit_log"):
        deploy_data_agent.validate_sources("test-project", references, "token", requester)
