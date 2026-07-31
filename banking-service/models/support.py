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

from sqlalchemy import Column, String, DateTime, JSON
from utils.database import UniversalUUID as UUID, generate_uuid
from datetime import datetime, timezone
from utils.database import Base

class Escalation(Base):
    __tablename__ = "support_escalations"
    __table_args__ = {'schema': 'operations'}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    room_name = Column(String, nullable=False)
    customer_id = Column(String, nullable=False)
    reason = Column(String, nullable=True)
    status = Column(String, default="PENDING")  # PENDING, ACCEPTED, COMPLETED, ABANDONED
    transcript = Column(JSON, nullable=True)     # Store conversation history
    assigned_to = Column(String, nullable=True)  # Email of the agent who accepted it
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
