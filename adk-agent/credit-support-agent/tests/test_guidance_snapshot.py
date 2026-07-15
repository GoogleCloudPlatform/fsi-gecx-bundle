from agent.guidance_snapshot import guidance_observability_payload


def test_guidance_observability_payload_excludes_prompt_and_topic_content() -> None:
    payload = guidance_observability_payload(
        {
            "schema_version": 1,
            "snapshot_id": "snapshot-1",
            "source": "knowledge_catalog",
            "topic_ids": ["fraud_golden_path"],
            "content_version": "2.0",
            "retrieved_at": "2026-07-14T12:00:00Z",
            "fallback_reason": None,
            "freshness": {
                "status": "FRESH",
                "oldest_last_reviewed": "2026-07-09",
            },
            "topics": [{"must_do": ["internal guidance"]}],
            "agent_guidance_summary": "private prompt material",
        }
    )

    assert payload["source"] == "knowledge_catalog"
    assert payload["freshness_status"] == "FRESH"
    assert "topics" not in payload
    assert "agent_guidance_summary" not in payload
