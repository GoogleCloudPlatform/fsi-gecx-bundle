from services.knowledge_catalog import KnowledgeCatalogService


def test_local_guidance_bundle_for_voice_fraud_returns_expected_topics():
    service = KnowledgeCatalogService()
    bundle = service.get_guidance_bundle_for_voice_fraud()

    assert bundle["source"] == "local_file"
    assert bundle["schema_version"] == 1
    assert bundle["content_version"] == "2.0"
    assert bundle["snapshot_id"]
    assert bundle["retrieved_at"].endswith("Z")
    assert bundle["fallback_reason"] == "KNOWLEDGE_CATALOG_DISABLED"
    assert bundle["freshness"]["status"] == "FRESH"
    assert bundle["topic_ids"] == [
        "fraud_golden_path",
        "recognized_activity",
        "replacement_card",
        "wallet_provisioning",
        "human_escalation",
    ]
    assert "Fraud Golden Path" in bundle["agent_guidance_summary"]
    assert "get_open_fraud_alert" in bundle["agent_guidance_summary"]
    assert "triage_fraud_case" in bundle["agent_guidance_summary"]
    assert "Ask whether the customer recognizes the suspicious charges" in bundle["agent_guidance_summary"]
    assert "Before opening a fraud case" in bundle["agent_guidance_summary"]
    assert "case is being raised with the fraud investigation team" in bundle["agent_guidance_summary"]
    assert "Do not sequence low-level fraud mitigation tools" in bundle["agent_guidance_summary"]


def test_local_guidance_bundle_filters_unknown_topics():
    service = KnowledgeCatalogService()
    bundle = service.get_guidance_bundle(["replacement_card", "missing_topic"], audience="CREDIT_SUPPORT_AGENT", channel="VOICE")

    assert bundle["topic_ids"] == ["replacement_card"]
    assert len(bundle["topics"]) == 1
    assert bundle["topics"][0]["topic_id"] == "replacement_card"


def test_snapshot_id_is_stable_across_retrieval_time():
    service = KnowledgeCatalogService()

    first = service.get_guidance_bundle_for_voice_fraud()
    second = service.get_guidance_bundle_for_voice_fraud()

    assert first["snapshot_id"] == second["snapshot_id"]


def test_catalog_failure_records_distinguishable_fallback(monkeypatch):
    service = KnowledgeCatalogService()
    service.enabled = True

    def fail_remote(*args, **kwargs):
        raise RuntimeError("catalog unavailable")

    monkeypatch.setattr(service, "_get_remote_topics", fail_remote)
    bundle = service.get_guidance_bundle_for_voice_fraud()

    assert bundle["source"] == "local_file_fallback"
    assert bundle["fallback_reason"] == "KNOWLEDGE_CATALOG_READ_FAILED"
    assert bundle["topic_ids"]


def test_partial_catalog_result_names_missing_remote_topics(monkeypatch):
    service = KnowledgeCatalogService()
    service.enabled = True
    local = service._get_local_topics(["fraud_golden_path"])
    monkeypatch.setattr(
        service,
        "_get_remote_topics",
        lambda *args, **kwargs: [local["fraud_golden_path"]],
    )

    bundle = service.get_guidance_bundle(
        ["fraud_golden_path", "wallet_provisioning"],
        audience="CREDIT_SUPPORT_AGENT",
        channel="VOICE",
    )

    assert bundle["source"] == "knowledge_catalog_with_local_fallback"
    assert bundle["fallback_reason"] == "MISSING_REMOTE_TOPICS:wallet_provisioning"
    assert bundle["topic_ids"] == ["fraud_golden_path", "wallet_provisioning"]


def test_guidance_freshness_detects_stale_content():
    freshness = KnowledgeCatalogService._guidance_freshness(
        [{"last_reviewed": "2025-01-01"}],
        __import__("datetime").date(2026, 7, 14),
    )

    assert freshness["status"] == "STALE"
    assert freshness["age_days"] > freshness["max_age_days"]


def test_local_guidance_release_validation_passes_current_bundle():
    result = KnowledgeCatalogService().validate_local_guidance(strict_freshness=True)

    assert result["schema_version"] == 1
    assert result["bundle_version"] == "2.0"
    assert result["topic_count"] == 5


def test_aspect_data_to_dict_converts_nested_protobuf_values_to_plain_json():
    from google.protobuf import struct_pb2

    data = struct_pb2.Struct()
    data.update(
        {
            "topic_id": "fraud_golden_path",
            "title": "Fraud Golden Path",
            "must_do": ["confirm disputed transactions"],
            "tool_dependencies": ["triage_fraud_case"],
        }
    )

    parsed = KnowledgeCatalogService._aspect_data_to_dict(data)

    assert parsed == {
        "topic_id": "fraud_golden_path",
        "title": "Fraud Golden Path",
        "must_do": ["confirm disputed transactions"],
        "tool_dependencies": ["triage_fraud_case"],
    }


def test_aspect_data_to_dict_normalizes_sequence_values_to_plain_lists():
    parsed = KnowledgeCatalogService._to_plain_json(
        {
            "topic_id": "fraud_golden_path",
            "must_do": ("confirm disputed transactions", "call triage_fraud_case"),
            "nested": {
                "tool_dependencies": ("get_open_fraud_alert", "triage_fraud_case"),
            },
        }
    )

    assert parsed == {
        "topic_id": "fraud_golden_path",
        "must_do": ["confirm disputed transactions", "call triage_fraud_case"],
        "nested": {
            "tool_dependencies": ["get_open_fraud_alert", "triage_fraud_case"],
        },
    }


def test_voice_token_json_sanitizer_handles_protobuf_guidance_values():
    from fastapi.encoders import jsonable_encoder
    from google.protobuf import struct_pb2
    from routers.credit_card import _to_json_safe

    data = struct_pb2.Struct()
    data.update(
        {
            "topic_id": "fraud_golden_path",
            "must_do": ["confirm disputed transactions"],
        }
    )
    payload = {
        "fraud_context": {
            "support_guidance": {
                "topics": [data],
            },
        },
    }

    safe_payload = _to_json_safe(payload)

    assert safe_payload == {
        "fraud_context": {
            "support_guidance": {
                "topics": [
                    {
                        "topic_id": "fraud_golden_path",
                        "must_do": ["confirm disputed transactions"],
                    }
                ],
            },
        },
    }
    jsonable_encoder(safe_payload)
