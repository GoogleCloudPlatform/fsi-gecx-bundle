import json
import logging
import time
from contextlib import contextmanager
from typing import Iterator

from fastapi import HTTPException, status

from utils.redis_client import execute_redis_command

logger = logging.getLogger(__name__)

MAINTENANCE_KEY = "system:maintenance_mode"
DEFAULT_RESET_TTL_SECONDS = 180
DEFAULT_DRAIN_SECONDS = 2.0


def get_maintenance_state() -> dict | None:
    try:
        raw = execute_redis_command(lambda redis_client: redis_client.get(MAINTENANCE_KEY))
    except Exception as exc:
        logger.warning("Failed to read maintenance state from Redis: %s", exc)
        return None

    if not raw:
        return None

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {"active": True, "reason": "System maintenance is in progress."}

    if "active" not in payload:
        payload["active"] = True
    return payload


def is_maintenance_mode() -> bool:
    state = get_maintenance_state()
    return bool(state and state.get("active"))


def get_maintenance_message(default_message: str = "System maintenance is in progress. Please retry shortly.") -> str:
    state = get_maintenance_state()
    if not state:
        return default_message
    return state.get("message") or state.get("reason") or default_message


def enable_maintenance_mode(
    *,
    reason: str,
    message: str,
    ttl_seconds: int = DEFAULT_RESET_TTL_SECONDS,
) -> bool:
    payload = {
        "active": True,
        "reason": reason,
        "message": message,
        "started_at_epoch_ms": int(time.time() * 1000),
    }
    try:
        return bool(
            execute_redis_command(
                lambda redis_client: redis_client.set(MAINTENANCE_KEY, json.dumps(payload), ex=ttl_seconds)
            )
        )
    except Exception as exc:
        logger.warning("Failed to enable maintenance mode in Redis: %s", exc)
        return False


def disable_maintenance_mode() -> None:
    try:
        execute_redis_command(lambda redis_client: redis_client.delete(MAINTENANCE_KEY))
    except Exception as exc:
        logger.warning("Failed to clear maintenance state in Redis: %s", exc)


def ensure_system_writable(operation: str = "write operation") -> None:
    if not is_maintenance_mode():
        return

    detail = {
        "status": "MAINTENANCE",
        "message": get_maintenance_message(),
        "operation": operation,
    }
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)


@contextmanager
def maintenance_window(
    *,
    reason: str,
    message: str,
    ttl_seconds: int = DEFAULT_RESET_TTL_SECONDS,
    drain_seconds: float = DEFAULT_DRAIN_SECONDS,
) -> Iterator[None]:
    enable_maintenance_mode(reason=reason, message=message, ttl_seconds=ttl_seconds)
    if drain_seconds > 0:
        time.sleep(drain_seconds)
    try:
        yield
    finally:
        disable_maintenance_mode()
