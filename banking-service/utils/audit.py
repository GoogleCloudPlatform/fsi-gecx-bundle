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

import json
import logging
import datetime
import uuid
from sqlalchemy.orm import Session
from models.audit import AuditOutbox, OutboxRelayCheckpoint

logger = logging.getLogger(__name__)

def record_audit_event(
    db: Session,
    event_type: str,
    payload: dict,
    *,
    event_id: str | None = None,
    schema_version: int = 1,
    created_at: datetime.datetime | None = None,
) -> AuditOutbox:
    """
    Records an immutable append-only audit event inside the active database session transaction.
    Guarantees that the event is committed atomically with the state mutation.
    The asynchronous relay publishes committed rows; this function performs no
    network I/O.
    """
    outbox_entry = AuditOutbox(
        event_id=event_id or str(uuid.uuid4()),
        event_type=event_type,
        schema_version=schema_version,
        payload=json.dumps(payload, sort_keys=True, separators=(",", ":")),
        created_at=created_at or datetime.datetime.now(datetime.timezone.utc),
    )
    db.add(outbox_entry)
    db.flush()  # Flush to populate default IDs without committing the transaction
    logger.info(f"Recorded append-only outbox audit event {outbox_entry.event_id} ({event_type}) inside active transaction.")
    return outbox_entry


def prune_historical_audit_events(db: Session, retention_days: int = 30) -> int:
    """
    Prunes only outbox rows known to be behind the committed relay cursor.

    Long-term retention is maintained in catalog-native Iceberg audit tables;
    unrelayed rows are never eligible for deletion.
    """
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=retention_days)
    checkpoint = db.query(OutboxRelayCheckpoint).filter_by(relay_name="audit-events-v1").one_or_none()
    if checkpoint is None or checkpoint.last_created_at is None:
        return 0
    checkpoint_time = checkpoint.last_created_at
    if checkpoint_time.tzinfo is None:
        checkpoint_time = checkpoint_time.replace(tzinfo=datetime.timezone.utc)
    safe_cutoff = min(cutoff, checkpoint_time)
    deleted_count = db.query(AuditOutbox).filter(AuditOutbox.created_at < safe_cutoff).delete()
    db.commit()
    return deleted_count


def process_dlq_audit_events(db: Session, batch_size: int = 50) -> list[str]:
    """Compatibility no-op: the Pub/Sub/Dataflow DLQ is externally replayed."""
    return []
