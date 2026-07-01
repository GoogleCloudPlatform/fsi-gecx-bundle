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
import json
import logging
import datetime
from sqlalchemy.orm import Session
from models.audit import AuditOutbox

logger = logging.getLogger(__name__)

MAX_RETRIES = 5

_publisher_client = None

def get_publisher_client():
    global _publisher_client
    if _publisher_client is None:
        try:
            from google.cloud import pubsub_v1
            _publisher_client = pubsub_v1.PublisherClient()
        except Exception as e:
            logger.warning(f"Could not initialize Pub/Sub PublisherClient: {e}")
    return _publisher_client


def record_audit_event(db: Session, event_type: str, payload: dict) -> AuditOutbox:
    """
    Records an immutable append-only audit event inside the active database session transaction.
    Guarantees that the event is committed atomically with the state mutation for WAL CDC ingestion.
    """
    outbox_entry = AuditOutbox(
        event_type=event_type,
        payload=json.dumps(payload),
    )
    db.add(outbox_entry)
    db.flush()  # Flush to populate default IDs without committing the transaction
    logger.info(f"Recorded append-only outbox audit event {outbox_entry.event_id} ({event_type}) inside active transaction.")
    return outbox_entry


def publish_pending_audit_events(db: Session, batch_size: int = 50) -> int:
    """
    In our WAL CDC architecture (Architecture Two), outbox ingestion occurs via zero-load WAL streaming without database polling.
    Returns the count of recent audit events in the append-only operational log.
    """
    logger.info("Outbox ingestion is managed via zero-load Datastream WAL CDC streaming.")
    return db.query(AuditOutbox).count()


def process_dlq_audit_events(db: Session, batch_size: int = 50) -> list[str]:
    """
    In our WAL CDC architecture, replication latency and DLQs are monitored at the infrastructure WAL stream level.
    """
    return []


def prune_historical_audit_events(db: Session, retention_days: int = 30) -> int:
    """
    Prunes historical append-only audit events older than retention_days from the operational database buffer.
    Long-term regulatory retention (7-10 years) is maintained in BigQuery compliance datasets via Datastream WAL CDC.
    """
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=retention_days)
    deleted_count = db.query(AuditOutbox).filter(AuditOutbox.created_at < cutoff).delete()
    db.commit()
    return deleted_count
