from types import SimpleNamespace

import pytest

from agent import readiness


@pytest.mark.asyncio
async def test_readiness_report_covers_runtime_dependencies(monkeypatch) -> None:
    async def session_store():
        return {"ok": True, "backend": "DatabaseSessionService", "durable": True}

    async def http_probe(**kwargs):
        return {"ok": True, "status": 200}

    async def customer_probe():
        return SimpleNamespace(
            voice_context={
                "has_active_fraud_alert": True,
                "reset_generation": {"token": "1:2"},
            },
            support_guidance={
                "source": "knowledge_catalog",
                "topic_ids": ["fraud_golden_path"],
                "content_version": "2.1",
                "freshness": {"status": "FRESH"},
            },
        )

    monkeypatch.setattr(readiness, "_probe_session_store", session_store)
    monkeypatch.setattr(readiness, "_probe_http", http_probe)
    report = await readiness.build_readiness_report(
        runtime_config=SimpleNamespace(
            audio_model="audio-model",
            video_model="video-model",
            livekit_url="ws://livekit",
            max_concurrent_sessions=2,
        ),
        banking_service_url="https://banking",
        banking_service_mcp_url="https://banking/api/mcp/",
        authorization_header="Bearer token",
        customer_probe=customer_probe,
        deployment_metadata={"revision": "credit-support-agent-00042"},
    )

    assert report["status"] == "ready"
    assert report["deployment"]["revision"] == "credit-support-agent-00042"
    assert report["checks"]["configuration"]["audio_model"] == "audio-model"
    assert report["checks"]["session_store"]["durable"] is True
    assert report["checks"]["customer_context"]["guidance_source"] == (
        "knowledge_catalog"
    )


@pytest.mark.asyncio
async def test_readiness_fails_closed_without_audio_model(monkeypatch) -> None:
    async def session_store():
        return {"ok": True}

    async def http_probe(**kwargs):
        return {"ok": True, "status": 200}

    monkeypatch.setattr(readiness, "_probe_session_store", session_store)
    monkeypatch.setattr(readiness, "_probe_http", http_probe)
    report = await readiness.build_readiness_report(
        runtime_config=SimpleNamespace(
            audio_model=None,
            video_model=None,
            livekit_url="ws://livekit",
            max_concurrent_sessions=2,
        ),
        banking_service_url="https://banking",
        banking_service_mcp_url="https://banking/api/mcp/",
        authorization_header=None,
    )

    assert report["status"] == "not_ready"
    assert report["checks"]["configuration"]["ok"] is False
