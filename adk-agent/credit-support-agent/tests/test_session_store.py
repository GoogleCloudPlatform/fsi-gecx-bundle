from google.adk.sessions import InMemorySessionService
import pytest

from agent.session_store import (
    BoundedDatabaseSessionService,
    cleanup_expired_sessions,
    open_or_resume_session,
    session_is_resumable,
    with_persistence_metadata,
)


def test_session_resumption_requires_matching_reset_generation():
    state = with_persistence_metadata({}, "4:2", now=100)
    assert session_is_resumable(
        state, reset_generation_token="4:2", now=101
    ) == (True, "RESUMABLE")
    assert session_is_resumable(
        state, reset_generation_token="5:0", now=101
    ) == (False, "RESET_GENERATION_CHANGED")


@pytest.mark.asyncio
async def test_open_or_resume_preserves_incomplete_session():
    service = InMemorySessionService()
    _, resumed, _ = await open_or_resume_session(
        service,
        user_id="user-1",
        session_id="session-1",
        state={"fraud_playbook": {"completion_status": "ACTIVE"}},
        reset_generation_token="1:0",
    )
    assert resumed is False
    session, resumed, reason = await open_or_resume_session(
        service,
        user_id="user-1",
        session_id="session-1",
        state={},
        reset_generation_token="1:0",
    )
    assert resumed is True
    assert reason == "RESUMABLE"
    assert session.state["fraud_playbook"]["completion_status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_reset_generation_replaces_stale_session():
    service = InMemorySessionService()
    await open_or_resume_session(
        service,
        user_id="user-1",
        session_id="session-1",
        state={"marker": "old"},
        reset_generation_token="1:0",
    )
    session, resumed, reason = await open_or_resume_session(
        service,
        user_id="user-1",
        session_id="session-1",
        state={"marker": "new"},
        reset_generation_token="2:0",
    )
    assert resumed is False
    assert reason == "RESET_GENERATION_CHANGED"
    assert session.state["marker"] == "new"


@pytest.mark.asyncio
async def test_cleanup_deletes_expired_sessions(monkeypatch):
    monkeypatch.setenv("VOICE_SESSION_TTL_SECONDS", "10")
    service = InMemorySessionService()
    await service.create_session(
        app_name="credit-support-agent",
        user_id="user-1",
        session_id="expired",
        state=with_persistence_metadata({}, "1:0", now=100),
    )
    assert await cleanup_expired_sessions(service, now=111) == 1
    assert (
        await service.get_session(
            app_name="credit-support-agent",
            user_id="user-1",
            session_id="expired",
        )
        is None
    )


@pytest.mark.asyncio
async def test_new_service_instance_resumes_incomplete_database_session(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}"
    first_service = BoundedDatabaseSessionService(db_url=db_url, max_events=10)
    await open_or_resume_session(
        first_service,
        user_id="user-1",
        session_id="durable-session",
        state={"fraud_playbook": {"completion_status": "ACTIVE"}},
        reset_generation_token="2:4",
    )
    await first_service.db_engine.dispose()

    replacement_service = BoundedDatabaseSessionService(
        db_url=db_url, max_events=10
    )
    session, resumed, reason = await open_or_resume_session(
        replacement_service,
        user_id="user-1",
        session_id="durable-session",
        state={},
        reset_generation_token="2:4",
    )
    assert resumed is True
    assert reason == "RESUMABLE"
    assert session.state["fraud_playbook"]["completion_status"] == "ACTIVE"
    await replacement_service.db_engine.dispose()
