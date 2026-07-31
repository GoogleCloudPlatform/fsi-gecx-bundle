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

import os

from fastapi import HTTPException, status

from utils.runtime import is_local_dev


def get_internal_switch_token() -> str:
    token = os.getenv("CARD_NETWORK_SWITCH_TOKEN")
    if token:
        return token
    if is_local_dev():
        return "switch-secret-key-12345"
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Data generator is not configured.",
    )


def is_valid_internal_switch_token(candidate: str | None) -> bool:
    return bool(candidate) and candidate == get_internal_switch_token()
