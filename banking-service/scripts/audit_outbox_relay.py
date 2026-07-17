# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Bounded at-least-once AlloyDB audit outbox relay."""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from google.cloud import pubsub_v1
from sqlalchemy import and_, or_, text
from sqlalchemy.orm import Session

from models.audit import AuditOutbox, OutboxRelayCheckpoint
from utils.database import SessionLocal


logger = logging.getLogger(__name__)
DEFAULT_RELAY_NAME = "audit-events-v1"
ADVISORY_LOCK_ID = 719042031


def _utc_iso(value: datetime.datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc).isoformat()


@dataclass(frozen=True)
class RelayResult:
    relay_name: str
    published: int
    last_event_id: str | None
    last_created_at: str | None
    status: str


class AuditOutboxRelay:
    def __init__(
        self,
        db: Session,
        publisher: Any,
        topic_path: str,
        *,
        relay_name: str = DEFAULT_RELAY_NAME,
        publish_timeout_seconds: float = 30.0,
    ) -> None:
        self.db = db
        self.publisher = publisher
        self.topic_path = topic_path
        self.relay_name = relay_name
        self.publish_timeout_seconds = publish_timeout_seconds

    def _acquire_singleton_lock(self) -> bool:
        if not self.db.bind or self.db.bind.dialect.name != "postgresql":
            return True
        return bool(
            self.db.execute(
                text("SELECT pg_try_advisory_xact_lock(:lock_id)"),
                {"lock_id": ADVISORY_LOCK_ID},
            ).scalar()
        )

    def _checkpoint(self) -> OutboxRelayCheckpoint:
        query = self.db.query(OutboxRelayCheckpoint).filter(
            OutboxRelayCheckpoint.relay_name == self.relay_name
        )
        if self.db.bind and self.db.bind.dialect.name != "sqlite":
            query = query.with_for_update()
        checkpoint = query.one_or_none()
        if checkpoint:
            return checkpoint
        checkpoint = OutboxRelayCheckpoint(relay_name=self.relay_name)
        self.db.add(checkpoint)
        self.db.flush()
        return checkpoint

    def _pending_rows(
        self, checkpoint: OutboxRelayCheckpoint, batch_size: int
    ) -> list[AuditOutbox]:
        query = self.db.query(AuditOutbox).filter(AuditOutbox.created_at.isnot(None))
        if checkpoint.last_created_at is not None:
            query = query.filter(
                or_(
                    AuditOutbox.created_at > checkpoint.last_created_at,
                    and_(
                        AuditOutbox.created_at == checkpoint.last_created_at,
                        AuditOutbox.event_id > (checkpoint.last_event_id or ""),
                    ),
                )
            )
        return (
            query.order_by(AuditOutbox.created_at.asc(), AuditOutbox.event_id.asc())
            .limit(batch_size)
            .all()
        )

    def _message(self, row: AuditOutbox) -> bytes:
        envelope = {
            "event_id": row.event_id,
            "event_type": row.event_type,
            "schema_version": int(row.schema_version or 1),
            "payload": row.payload,
            "created_at": _utc_iso(row.created_at),
            "published_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "source": "alloydb.audit.audit_outbox",
        }
        return json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def run(self, *, batch_size: int = 100, dry_run: bool = False) -> RelayResult:
        if batch_size < 1 or batch_size > 1000:
            raise ValueError("batch_size must be between 1 and 1000")
        if not self._acquire_singleton_lock():
            self.db.rollback()
            return RelayResult(self.relay_name, 0, None, None, "already_running")

        checkpoint = self._checkpoint()
        rows = self._pending_rows(checkpoint, batch_size)
        if dry_run:
            self.db.rollback()
            last = rows[-1] if rows else None
            return RelayResult(
                self.relay_name,
                len(rows),
                last.event_id if last else checkpoint.last_event_id,
                _utc_iso(last.created_at if last else checkpoint.last_created_at),
                "dry_run",
            )

        published = 0
        try:
            for row in rows:
                future = self.publisher.publish(
                    self.topic_path,
                    self._message(row),
                    event_id=row.event_id,
                    event_type=row.event_type,
                    schema_version=str(row.schema_version or 1),
                )
                future.result(timeout=self.publish_timeout_seconds)
                published += 1

            if rows:
                last = rows[-1]
                checkpoint.last_created_at = last.created_at
                checkpoint.last_event_id = last.event_id
                checkpoint.published_count = int(checkpoint.published_count or 0) + published
                checkpoint.updated_at = datetime.datetime.now(datetime.timezone.utc)
            self.db.commit()
        except Exception:
            # Previously acknowledged messages may be delivered again because
            # the cursor is committed only after the whole bounded batch.
            self.db.rollback()
            logger.exception(
                "audit_outbox_relay_failed relay=%s published_before_failure=%d",
                self.relay_name,
                published,
            )
            raise

        result = RelayResult(
            self.relay_name,
            published,
            checkpoint.last_event_id,
            _utc_iso(checkpoint.last_created_at),
            "ok",
        )
        logger.info("audit_outbox_relay_summary %s", json.dumps(result.__dict__, sort_keys=True))
        return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("AUDIT_RELAY_BATCH_SIZE", "100")))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    project_id = os.getenv("PROJECT_ID", "").strip()
    topic_id = os.getenv("AUDIT_EVENTS_TOPIC", "audit-events").strip()
    if not project_id:
        raise RuntimeError("PROJECT_ID is required")
    if os.getenv("AUDIT_RELAY_ENABLED", "true").lower() not in {"1", "true", "yes", "on"}:
        print(json.dumps({"status": "disabled"}))
        return

    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(project_id, topic_id)
    with SessionLocal() as db:
        result = AuditOutboxRelay(db, publisher, topic_path).run(
            batch_size=args.batch_size,
            dry_run=args.dry_run,
        )
    print(json.dumps(result.__dict__, sort_keys=True))


if __name__ == "__main__":
    main()
