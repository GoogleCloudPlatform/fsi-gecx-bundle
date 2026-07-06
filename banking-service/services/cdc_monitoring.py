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
import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.credit_card import PostedTransaction, TransactionAuthorization
from repositories.cdc_lakehouse import CdcLakehouseRepository

logger = logging.getLogger(__name__)


class CdcMonitoringService:
    """Service layer for operational-to-lakehouse CDC monitoring."""

    def __init__(self, db: Session, lakehouse_repo: CdcLakehouseRepository | None = None):
        self.db = db
        self.lakehouse_repo = lakehouse_repo or CdcLakehouseRepository()

    @staticmethod
    def _ensure_aware(value):
        if value and value.tzinfo is None:
            return value.replace(tzinfo=datetime.timezone.utc)
        return value

    def get_operational_latest_timestamp(self):
        latest_auth = self.db.query(func.max(TransactionAuthorization.created_at)).scalar()
        latest_posted = self.db.query(func.max(PostedTransaction.posted_at)).scalar()
        return max([dt for dt in [latest_auth, latest_posted] if dt], default=None)

    def get_cdc_status(self) -> dict:
        operational_latest = self.get_operational_latest_timestamp()
        lakehouse_latest = None
        lakehouse_count = 0
        bq_error = None

        try:
            watermark = self.lakehouse_repo.get_cdc_watermark()
            if watermark:
                lakehouse_latest = watermark.get("latest_ts")
                lakehouse_count = int(watermark.get("row_count") or 0)
        except Exception as exc:
            logger.warning(f"Unable to query BigQuery CDC status: {exc}")
            bq_error = str(exc)

        lag_seconds = None
        operational_latest = self._ensure_aware(operational_latest)
        lakehouse_latest = self._ensure_aware(lakehouse_latest)
        if operational_latest and lakehouse_latest:
            lag_seconds = max(0, int((operational_latest - lakehouse_latest).total_seconds()))

        return {
            "status": "SUCCESS" if not bq_error else "DEGRADED",
            "operational_latest_timestamp": operational_latest.isoformat() if operational_latest else None,
            "lakehouse_latest_timestamp": lakehouse_latest.isoformat() if lakehouse_latest else None,
            "replication_lag_seconds": lag_seconds,
            "lakehouse_row_count": lakehouse_count,
            "bigquery_dataset": self.lakehouse_repo.dataset,
            "bigquery_error": bq_error,
        }

    def get_lakehouse_stream(self) -> dict:
        try:
            rows = self.lakehouse_repo.list_recent_transactions(limit=20)
        except Exception as exc:
            logger.warning(f"Unable to query BigQuery CDC stream: {exc}")
            return {"status": "DEGRADED", "stream": [], "bigquery_error": str(exc)}

        stream_items = []
        for row in rows:
            event_time = row.get("event_time")
            stream_items.append({
                "id": row.get("id"),
                "rrn": row.get("rrn") or "N/A",
                "timestamp": event_time.strftime("%H:%M:%S") if event_time else "N/A",
                "merchant_name": row.get("merchant_name"),
                "amount_cents": row.get("amount_cents"),
                "status": row.get("status"),
                "bq_view": row.get("source"),
                "raw_time": event_time.timestamp() if event_time else 0,
            })

        return {"status": "SUCCESS", "stream": stream_items}
