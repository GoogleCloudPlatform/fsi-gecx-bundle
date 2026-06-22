from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from utils.database import get_db
from models.settings import SystemSetting
from repositories.settings import SystemSettingsRepository
from utils.auth import get_current_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["System Settings"], dependencies=[Depends(get_current_user)])


def get_settings_repo(db: Session = Depends(get_db)) -> SystemSettingsRepository:
    """Dependency provider resolving the SystemSettingsRepository."""
    return SystemSettingsRepository(db)


@router.get("")
def get_all_settings(repo: SystemSettingsRepository = Depends(get_settings_repo)):
    """Retrieves all active system configuration settings."""
    logger.info("Retrieving active system settings...")
    settings = repo.list_all()
    return {s.key: s.value for s in settings}

@router.post("")
def update_settings(
    payload: dict,
    db: Session = Depends(get_db),
    repo: SystemSettingsRepository = Depends(get_settings_repo)
):
    """Updates the specified system configuration settings in database."""
    logger.info(f"Updating system settings parameters: {payload}")
    try:
        for key, value in payload.items():
            setting = repo.get_by_key(key)
            if setting:
                setting.value = str(value)
                repo.save(setting)
            else:
                setting = SystemSetting(key=key, value=str(value))
                repo.save(setting)
        db.commit()
        logger.info("System settings parameters updated successfully.")
        return {"status": "SUCCESS", "updated_keys": list(payload.keys())}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save system settings: {e}")
        raise HTTPException(status_code=500, detail="Database save error.")
