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

from enum import Enum


INTERNAL_TOOL_RUNTIME_STATUS = "_TOOL_RUNTIME_STATUS"


class DataChannelEvent(str, Enum):
    CARD_STATUS_LOCK = "CARD_STATUS_LOCK"
    FRAUD_ALERT_INSPECTED = "FRAUD_ALERT_INSPECTED"
    CARD_REPLACED = "CARD_REPLACED"
    WALLET_PROVISIONING_QUEUED = "WALLET_PROVISIONING_QUEUED"
    FRAUD_ALERT_RESOLVED = "FRAUD_ALERT_RESOLVED"
    LIMIT_UPDATED = "LIMIT_UPDATED"
    FEE_REVERSED = "FEE_REVERSED"
    HIGHLIGHT_TRANSACTION = "HIGHLIGHT_TRANSACTION"
    SESSION_END = "SESSION_END"
    TRANSCRIPT = "TRANSCRIPT"
    HANDOFF_PENDING = "HANDOFF_PENDING"
    GUIDANCE_SNAPSHOT = "GUIDANCE_SNAPSHOT"
    CUSTOMER_TEXT_INPUT = "CUSTOMER_TEXT_INPUT"
    CUSTOMER_TEXT_ACCEPTED = "CUSTOMER_TEXT_ACCEPTED"
    CUSTOMER_TEXT_REJECTED = "CUSTOMER_TEXT_REJECTED"
    AVATAR_FALLBACK = "AVATAR_FALLBACK"
