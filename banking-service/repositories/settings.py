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

from typing import Optional, List
from sqlalchemy.orm import Session
from models.settings import SystemSetting

class SystemSettingsRepository:
    """
    Repository encapsulating persistence logic and database access for System Settings.
    """
    def __init__(self, db: Session):
        self.db = db

    def get_by_key(self, key: str) -> Optional[SystemSetting]:
        """Retrieves a system setting matching the specified unique key."""
        return self.db.query(SystemSetting).filter(SystemSetting.key == key).first()

    def get_first(self) -> Optional[SystemSetting]:
        """Retrieves the first available setting record. Useful for existence checking."""
        return self.db.query(SystemSetting).first()

    def list_all(self) -> List[SystemSetting]:
        """Retrieves all system settings records."""
        return self.db.query(SystemSetting).all()

    def save(self, setting: SystemSetting) -> SystemSetting:
        """Adds a new system setting instance or flushes state modifications."""
        self.db.add(setting)
        self.db.flush()
        return setting
