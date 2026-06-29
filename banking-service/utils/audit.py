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
    Records an audit event inside the active database session transaction.
    Guarantees that the event is committed atomically with the state mutation.
    """
    outbox_entry = AuditOutbox(
        event_type=event_type,
        payload=json.dumps(payload),
        status="PENDING",
        retry_count=0,
    )
    db.add(outbox_entry)
    db.flush()  # Flush to populate default IDs without committing the transaction
    logger.info(f"Recorded outbox audit event {outbox_entry.event_id} ({event_type}) inside active transaction.")
    return outbox_entry


def publish_pending_audit_events(db: Session, batch_size: int = 50) -> int:
    """
    Queries pending outbox records and publishes them to Google Cloud Pub/Sub.
    Should be called asynchronously or via a background polling worker.
    """
    pending_records = db.query(AuditOutbox).filter(AuditOutbox.status == "PENDING").limit(batch_size).all()
    if not pending_records:
        return 0

    publisher = get_publisher_client()
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    topic_name = os.getenv("PUBSUB_TOPIC_AUDIT")
    
    topic_path = None
    if publisher and project_id and topic_name:
        topic_path = publisher.topic_path(project_id, topic_name)

    published_count = 0
    for record in pending_records:
        try:
            if topic_path:
                raw_p = json.loads(record.payload) if isinstance(record.payload, str) else record.payload
                message_dict = {
                    "event_id": str(record.event_id),
                    "event_type": record.event_type,
                    "created_at": record.created_at.isoformat() if record.created_at else datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "payload": raw_p if isinstance(raw_p, (dict, list)) else {"raw": str(raw_p)},
                }
                if isinstance(raw_p, dict):
                    for k in ["application_id", "artifact_id", "underwriter_id", "decision", "account_id", "user_id"]:
                        if k in raw_p and raw_p[k] is not None:
                            message_dict[k] = str(raw_p[k])
                data_bytes = json.dumps(message_dict).encode("utf-8")
                future = publisher.publish(
                    topic_path,
                    data_bytes,
                    event_id=record.event_id,
                    event_type=record.event_type,
                )
                future.result(timeout=5.0)
            else:
                logger.debug(f"Simulating publish for audit event {record.event_id} (Pub/Sub topic unconfigured).")

            record.status = "PUBLISHED"
            record.published_at = datetime.datetime.now(datetime.timezone.utc)
            published_count += 1
        except Exception as e:
            record.retry_count += 1
            logger.error(f"Failed to publish audit event {record.event_id} (attempt {record.retry_count}): {e}")
            if record.retry_count >= MAX_RETRIES:
                record.status = "DLQ"  # Routed to DLQ for dead-letter alerting & manual intervention
                logger.critical(f"Audit event {record.event_id} exceeded max retries ({MAX_RETRIES}) and moved to DLQ state.")

    db.commit()
    return published_count


def process_dlq_audit_events(db: Session, batch_size: int = 50) -> list[str]:
    """
    Sweeps dead-letter queue (DLQ/FAILED) outbox records, emits alert monitoring metrics,
    and returns a list of dead-lettered event IDs requiring intervention.
    """
    dlq_records = db.query(AuditOutbox).filter(AuditOutbox.status.in_(["DLQ", "FAILED"])).limit(batch_size).all()
    event_ids = []
    for rec in dlq_records:
        logger.warning(f"DLQ Monitoring Alert: Event ID {rec.event_id} ({rec.event_type}) in state {rec.status} with {rec.retry_count} retries.")
        event_ids.append(rec.event_id)
    return event_ids
