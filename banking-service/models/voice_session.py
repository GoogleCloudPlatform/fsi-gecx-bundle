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

"""Banking-owned reset epoch state in the otherwise ADK-owned session schema."""

from sqlalchemy import BigInteger, Column, DateTime, String, text

from utils.database import Base


class VoiceSessionResetEpoch(Base):
    __tablename__ = "reset_epochs"
    __table_args__ = {"schema": "voice_support_sessions"}

    scope_type = Column(String(16), primary_key=True)
    scope_id = Column(String(255), primary_key=True)
    epoch = Column(BigInteger, nullable=False, server_default=text("0"))
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
