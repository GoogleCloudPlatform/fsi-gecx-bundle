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
