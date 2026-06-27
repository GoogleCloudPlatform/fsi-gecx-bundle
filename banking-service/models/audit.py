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

import uuid
import datetime
from sqlalchemy import Column, String, Text, DateTime, Integer, Index
from sqlalchemy.dialects.postgresql import UUID
from utils.database import Base


class AuditOutbox(Base):
    """
    Transactional outbox table for reliable asynchronous event publishing to Pub/Sub.
    Ensures zero loss of compliance audit events by persisting state changes and audit events within the same ACID transaction.
    """
    __tablename__ = "audit_outbox"
    __table_args__ = (
        Index("idx_audit_outbox_status", "status"),
        Index("idx_audit_outbox_event_id", "event_id"),
        {'schema': 'ledger'},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(String(128), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    event_type = Column(String(100), nullable=False)
    payload = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="PENDING")  # 'PENDING', 'PUBLISHED', 'FAILED'
    retry_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    published_at = Column(DateTime, nullable=True)
