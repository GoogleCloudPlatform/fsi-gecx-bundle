import os
import redis
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_redis_client = None
_redis_disabled = False


def reset_redis_client() -> None:
    """Drop the cached Redis client after a broken pooled connection."""
    global _redis_client
    global _redis_disabled

    if _redis_client is not None:
        try:
            _redis_client.connection_pool.disconnect()
        except Exception:
            pass
    _redis_client = None
    _redis_disabled = False

def get_redis_client() -> Optional[redis.Redis]:
    global _redis_client
    global _redis_disabled

    if _redis_disabled:
        return None

    if _redis_client is None:
        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", 6379))
        password = os.getenv("REDIS_PASSWORD")
        
        try:
            _redis_client = redis.Redis(
                host=host,
                port=port,
                password=password,
                decode_responses=True,
                ssl=(port == 6378),
                ssl_cert_reqs="none",
                health_check_interval=30,
                socket_keepalive=True,
                retry_on_timeout=True,
                socket_connect_timeout=0.25,
                socket_timeout=0.25,
            )
            # Test connection
            _redis_client.ping()
        except Exception as e:
            logger.warning(f"Could not initialize Redis client: {e}")
            _redis_client = None
            _redis_disabled = True
    return _redis_client


def execute_redis_command(operation):
    client = get_redis_client()
    if not client:
        return None

    try:
        return operation(client)
    except (redis.ConnectionError, redis.TimeoutError):
        reset_redis_client()
        client = get_redis_client()
        if not client:
            return None
        return operation(client)
