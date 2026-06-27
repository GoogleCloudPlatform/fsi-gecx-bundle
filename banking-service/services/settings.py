# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
from typing import Dict, Any, List
from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.settings import SystemSetting
from repositories.settings import SystemSettingsRepository

logger = logging.getLogger(__name__)


class SettingsService:
    """Service layer encapsulating dynamic system parameter configurations."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = SystemSettingsRepository(db)

    def get_all_settings(self) -> Dict[str, str]:
        logger.info("Retrieving active system settings...")
        settings = self.repo.list_all()
        return {s.key: s.value for s in settings}

    def update_settings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        logger.info(f"Updating system settings parameters: {payload}")
        try:
            for key, value in payload.items():
                setting = self.repo.get_by_key(key)
                if setting:
                    setting.value = str(value)
                    self.repo.save(setting)
                else:
                    setting = SystemSetting(key=key, value=str(value))
                    self.repo.save(setting)
            self.db.commit()
            logger.info("System settings parameters updated successfully.")
            return {"status": "SUCCESS", "updated_keys": list(payload.keys())}
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to save system settings: {e}")
            raise HTTPException(status_code=500, detail="Database save error.")
