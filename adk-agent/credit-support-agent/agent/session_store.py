"""Persistent, bounded ADK session storage for the voice-support runtime."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import os
import time
from typing import Any

from google.adk.sessions import DatabaseSessionService, InMemorySessionService
from google.adk.sessions.base_session_service import GetSessionConfig

APP_NAME = "credit-support-agent"
SESSION_SCHEMA = "voice_support_sessions"
DEFAULT_TTL_SECONDS = 60 * 60 * 12
DEFAULT_MAX_EVENTS = 120


class BoundedDatabaseSessionService(DatabaseSessionService):
    """Database service that never hydrates an unbounded transcript."""

    def __init__(self, *args, max_events: int = DEFAULT_MAX_EVENTS, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_events = max_events

    async def get_session(self, *, app_name, user_id, session_id, config=None):
        return await super().get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
            config=config or GetSessionConfig(num_recent_events=self.max_events),
        )


def _completion_status(state: dict[str, Any]) -> str:
    playbook = state.get("fraud_playbook") or {}
    return str(playbook.get("completion_status") or "ACTIVE").upper()


def session_is_resumable(
    state: dict[str, Any],
    *,
    reset_generation_token: str,
    now: float | None = None,
) -> tuple[bool, str]:
    metadata = state.get("persistence") or {}
    if str(metadata.get("reset_generation_token") or "") != reset_generation_token:
        return False, "RESET_GENERATION_CHANGED"
    if _completion_status(state) in {"COMPLETED", "EXPIRED"}:
        return False, "SESSION_COMPLETED"
    expires_at = float(metadata.get("expires_at") or 0)
    if expires_at and expires_at <= (now if now is not None else time.time()):
        return False, "SESSION_EXPIRED"
    return True, "RESUMABLE"


def with_persistence_metadata(
    state: dict[str, Any], reset_generation_token: str, *, now: float | None = None
) -> dict[str, Any]:
    created_at = now if now is not None else time.time()
    enriched = dict(state)
    enriched["reset_generation_token"] = reset_generation_token
    enriched["persistence"] = {
        "schema_version": 1,
        "created_at": datetime.fromtimestamp(created_at, tz=timezone.utc).isoformat(),
        "expires_at": created_at
        + int(os.getenv("VOICE_SESSION_TTL_SECONDS", str(DEFAULT_TTL_SECONDS))),
        "reset_generation_token": reset_generation_token,
    }
    return enriched


async def open_or_resume_session(
    service,
    *,
    user_id: str,
    session_id: str,
    state: dict[str, Any],
    reset_generation_token: str,
) -> tuple[Any, bool, str]:
    existing = await service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if existing is not None:
        resumable, reason = session_is_resumable(
            existing.state,
            reset_generation_token=reset_generation_token,
        )
        if resumable:
            return existing, True, reason
        await service.delete_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
    else:
        reason = "SESSION_NOT_FOUND"

    created = await service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
        state=with_persistence_metadata(state, reset_generation_token),
    )
    return created, False, reason


async def cleanup_expired_sessions(service, *, now: float | None = None) -> int:
    """Delete expired or completed sessions; safe to run opportunistically."""
    response = await service.list_sessions(app_name=APP_NAME)
    deleted = 0
    current_time = now if now is not None else time.time()
    for session in response.sessions:
        metadata = session.state.get("persistence") or {}
        expires_at = float(metadata.get("expires_at") or 0)
        if _completion_status(session.state) in {"COMPLETED", "EXPIRED"} or (
            expires_at and expires_at <= current_time
        ):
            await service.delete_session(
                app_name=APP_NAME,
                user_id=session.user_id,
                session_id=session.id,
            )
            deleted += 1
    return deleted


_session_service = None
_session_service_lock = asyncio.Lock()


async def get_session_service():
    """Create one process-wide async session service, with a local fallback."""
    global _session_service
    if _session_service is not None:
        return _session_service
    async with _session_service_lock:
        if _session_service is not None:
            return _session_service
        db_url = os.getenv("DATABASE_URL")
        persistence_enabled = os.getenv("VOICE_SESSION_PERSISTENCE_ENABLED", "true").lower()
        if (
            not db_url
            or not db_url.startswith("postgresql")
            or persistence_enabled not in {"1", "true", "yes", "on"}
        ):
            _session_service = InMemorySessionService()
            return _session_service

        max_events = int(os.getenv("VOICE_SESSION_MAX_EVENTS", str(DEFAULT_MAX_EVENTS)))
        if os.getenv("DB_IAM_AUTH", "false").lower() == "true":
            _session_service = await _create_iam_database_service(db_url, max_events)
        else:
            async_url = db_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
            _session_service = BoundedDatabaseSessionService(
                db_url=async_url,
                max_events=max_events,
                connect_args={"server_settings": {"search_path": SESSION_SCHEMA}},
            )
        await _session_service.prepare_tables()
        return _session_service


async def _create_iam_database_service(db_url: str, max_events: int):
    import asyncpg
    import google.auth
    import google.auth.transport.requests
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import create_async_engine

    url = make_url(db_url)

    async def async_creator():
        credentials, _ = google.auth.default(
            scopes=[
                "https://www.googleapis.com/auth/sqlservice.login",
                "https://www.googleapis.com/auth/cloud-platform",
            ]
        )
        await asyncio.to_thread(
            credentials.refresh, google.auth.transport.requests.Request()
        )
        return await asyncpg.connect(
            user=url.username,
            password=credentials.token,
            database=url.database,
            host=url.host or url.query.get("host"),
            server_settings={"search_path": SESSION_SCHEMA},
        )

    engine = create_async_engine(
        "postgresql+asyncpg://",
        async_creator=async_creator,
        pool_pre_ping=True,
        pool_recycle=3000,
    )
    return BoundedDatabaseSessionService(
        db_engine=engine, max_events=max_events
    )
