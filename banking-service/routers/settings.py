import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from utils.database import get_db
from utils.auth import get_current_user
from services.settings import SettingsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["System Settings"], dependencies=[Depends(get_current_user)])


def get_settings_service(db: Session = Depends(get_db)) -> SettingsService:
    return SettingsService(db)


@router.get("")
def get_all_settings(service: SettingsService = Depends(get_settings_service)):
    return service.get_all_settings()


@router.post("")
def update_settings(
    payload: dict,
    service: SettingsService = Depends(get_settings_service)
):
    return service.update_settings(payload)
