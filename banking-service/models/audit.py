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
from sqlalchemy import Column, String, Text, DateTime, Index
from utils.database import UniversalUUID as UUID, generate_uuid
from utils.database import Base


class AuditOutbox(Base):
    """
    Append-only transactional event log table (`audit.audit_outbox`) for zero-load WAL CDC streaming to BigQuery.
    Ensures zero loss of compliance audit events by persisting state changes and audit events within the same ACID transaction.
    In a WAL CDC architecture, rows are immutable append-only records without state mutations (no status/retry updates).
    """
    __tablename__ = "audit_outbox"
    __table_args__ = (
        Index("idx_audit_outbox_created_at", "created_at"),
        Index("idx_audit_outbox_event_type", "event_type"),
        {'schema': 'audit'},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    event_id = Column(String(128), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    event_type = Column(String(100), nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

# Type alias for descriptive referencing in CDC architecture
AuditEventLog = AuditOutbox
