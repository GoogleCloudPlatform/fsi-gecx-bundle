import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.fraud_alerts import FraudAlertService
from utils.database import SessionLocal, enable_session_rbac_override

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s.", name, raw, default)
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _env_sources() -> list[str]:
    raw = os.getenv(
        "FRAUD_ALERT_LIFECYCLE_SOURCES",
        "MODEL_DETECTED_FRAUD,SIMULATION_TARGETED_FRAUD",
    )
    return [source.strip() for source in raw.split(",") if source.strip()]


def main() -> None:
    max_age_minutes = _env_int("FRAUD_ALERT_NO_RESPONSE_MAX_AGE_MINUTES", 30)
    limit = _env_int("FRAUD_ALERT_LIFECYCLE_BATCH_LIMIT", 100)
    dry_run = _env_bool("FRAUD_ALERT_LIFECYCLE_DRY_RUN", False)
    db = SessionLocal()
    try:
        enable_session_rbac_override(db)
        result = FraudAlertService(db).expire_stale_open_alerts(
            max_age_minutes=max_age_minutes,
            limit=limit,
            sources=_env_sources(),
            dry_run=dry_run,
        )
        logger.info("Fraud alert lifecycle sweep completed: %s", result)
    finally:
        db.close()


if __name__ == "__main__":
    main()
