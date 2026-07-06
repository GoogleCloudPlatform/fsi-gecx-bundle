import os
import redis
import logging

logger = logging.getLogger(__name__)

_redis_client = None

def get_redis_client() -> redis.Redis:
    global _redis_client
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
                retry_on_timeout=True
            )
            # Test connection
            _redis_client.ping()
        except Exception as e:
            logger.warning(f"Could not initialize Redis client: {e}")
            # Fallback to a dummy client or let it fail depending on needs
            # For now, we return the disconnected client and let operations fail gracefully
    return _redis_client
