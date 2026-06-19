from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from utils.database import get_db
from models.settings import SystemSetting
from utils.auth import get_current_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["System Settings"], dependencies=[Depends(get_current_user)])

@router.get("")
def get_all_settings(db: Session = Depends(get_db)):
    """Retrieves all active system configuration settings."""
    logger.info("Retrieving active system settings...")
    settings = db.query(SystemSetting).all()
    return {s.key: s.value for s in settings}

@router.post("")
def update_settings(payload: dict, db: Session = Depends(get_db)):
    """Updates the specified system configuration settings in database."""
    logger.info(f"Updating system settings parameters: {payload}")
    try:
        for key, value in payload.items():
            setting = db.query(SystemSetting).filter_by(key=key).first()
            if setting:
                setting.value = str(value)
            else:
                setting = SystemSetting(key=key, value=str(value))
                db.add(setting)
        db.commit()
        logger.info("System settings parameters updated successfully.")
        return {"status": "SUCCESS", "updated_keys": list(payload.keys())}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save system settings: {e}")
        raise HTTPException(status_code=500, detail="Database save error.")
