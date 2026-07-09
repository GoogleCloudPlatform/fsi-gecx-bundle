from services.knowledge_catalog import KnowledgeCatalogService


def test_local_guidance_bundle_for_voice_fraud_returns_expected_topics():
    service = KnowledgeCatalogService()
    bundle = service.get_guidance_bundle_for_voice_fraud()

    assert bundle["source"] == "local_file"
    assert bundle["topic_ids"] == [
        "fraud_golden_path",
        "recognized_activity",
        "replacement_card",
        "wallet_provisioning",
        "human_escalation",
    ]
    assert "Fraud Golden Path" in bundle["agent_guidance_summary"]
    assert "get_open_fraud_alert" in bundle["agent_guidance_summary"]
    assert "Ask whether the customer recognizes the suspicious charges" in bundle["agent_guidance_summary"]
    assert "Before opening a fraud case" in bundle["agent_guidance_summary"]


def test_local_guidance_bundle_filters_unknown_topics():
    service = KnowledgeCatalogService()
    bundle = service.get_guidance_bundle(["replacement_card", "missing_topic"], audience="CREDIT_SUPPORT_AGENT", channel="VOICE")

    assert bundle["topic_ids"] == ["replacement_card"]
    assert len(bundle["topics"]) == 1
    assert bundle["topics"][0]["topic_id"] == "replacement_card"
