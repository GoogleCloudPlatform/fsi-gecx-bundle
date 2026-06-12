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

import datetime
from typing import Optional

from pydantic import BaseModel

SUPPORT_MESSAGE_TYPE = "support_message"
USER_MESSAGE_TYPE = "user_message"
SECURE_MESSAGES_TOPIC = "all_secure_messages"
SENDER_TYPE_USER = "user"
SENDER_TYPE_BANK = "bank"


class AdminReadRequest(BaseModel):
    message_ids: list[str]
    user_id: str


class SecureMessageCreateRequest(BaseModel):
    category: str
    message: str
    thread_id: Optional[str] = None
    user_id: Optional[str] = None
    sender: Optional[str] = SENDER_TYPE_USER


class SecureMessageResponse(BaseModel):
    message_id: str
    user_id: str
    sender: str
    category: str
    message: str
    created_at: datetime.datetime
    deleted: bool
    thread_id: str
    is_user_read: bool
    is_agent_read: bool
