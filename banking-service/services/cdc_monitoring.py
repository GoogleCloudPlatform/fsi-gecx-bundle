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
import json
import logging
import time

from google.cloud import monitoring_v3
from sqlalchemy import func
from sqlalchemy.orm import Session

from models.credit_card import PostedTransaction, TransactionAuthorization
from repositories.cdc_lakehouse import CdcLakehouseRepository
from repositories.fraud import FraudAlertRepository
from utils.database import enable_session_rbac_override
from utils.gcp import get_project_id
from utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)

_cache = get_redis_client()


class CdcMonitoringService:
    """Service layer for operational-to-lakehouse CDC monitoring."""

    def __init__(
        self,
        db: Session,
        lakehouse_repo: CdcLakehouseRepository | None = None,
        fraud_alert_repo: FraudAlertRepository | None = None,
    ):
        self.db = db
        self.lakehouse_repo = lakehouse_repo or CdcLakehouseRepository()
        self.fraud_alert_repo = fraud_alert_repo or FraudAlertRepository(db)
        self.project_id = get_project_id()

    @staticmethod
    def _ensure_aware(value):
        if value and value.tzinfo is None:
            return value.replace(tzinfo=datetime.timezone.utc)
        return value

    @staticmethod
    def _format_stream_row(row: dict) -> dict:
        event_time = row.get("event_time")
        event_time = CdcMonitoringService._ensure_aware(event_time)
        raw_time = event_time.timestamp() if event_time else None
        return {
            "id": row.get("id"),
            "rrn": row.get("rrn"),
            "timestamp": event_time.strftime("%H:%M:%S") if event_time else "N/A",
            "merchant_name": row.get("merchant_name"),
            "amount_cents": row.get("amount_cents"),
            "status": row.get("status"),
            "bq_view": row.get("source"),
            "raw_time": raw_time,
        }

    @staticmethod
    def _deserialize_event(value: str) -> dict | None:
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return None

    def _get_recent_operational_events(self, limit: int = 20) -> list[dict]:
        redis_client = get_redis_client()
        if not redis_client:
            return []

        try:
            recent_values = redis_client.lrange("recent_transactions", 0, max(0, limit - 1))
        except Exception as exc:
            logger.warning(f"Redis event bus read failed: {exc}")
            return []

        events = []
        for value in recent_values:
            event = self._deserialize_event(value)
            if event:
                events.append(event)
        return events

    def get_operational_latest_timestamp(self):
        enable_session_rbac_override(self.db)
        latest_auth = self.db.query(func.max(TransactionAuthorization.created_at)).scalar()
        latest_posted = self.db.query(func.max(PostedTransaction.posted_at)).scalar()
        return max([dt for dt in [latest_auth, latest_posted] if dt], default=None)

    def get_operational_stream(self, limit: int = 20) -> dict:
        return {"status": "SUCCESS", "stream": self._get_recent_operational_events(limit=limit)}

    def get_operational_stream_metrics(self, limit: int = 100) -> dict:
        now = time.time()
        events = self._get_recent_operational_events(limit=limit)
        raw_times = [float(event["raw_time"]) for event in events if event.get("raw_time") is not None]
        recent_events = [event for event in events if event.get("raw_time") is not None and (now - float(event["raw_time"])) <= 60]

        auth_count = sum(1 for event in recent_events if "HOLD" in str(event.get("status", "")) or "FLAGGED" in str(event.get("status", "")))
        posted_count = sum(1 for event in recent_events if "SETTLE" in str(event.get("status", "")))
        anomaly_count = sum(1 for event in recent_events if "FLAGGED" in str(event.get("status", "")))

        latest_event_ts = max(raw_times) if raw_times else None
        latest_event_dt = (
            datetime.datetime.fromtimestamp(latest_event_ts, tz=datetime.timezone.utc)
            if latest_event_ts
            else None
        )

        return {
            "events_per_minute": len(recent_events),
            "authorization_events_per_minute": auth_count,
            "posted_events_per_minute": posted_count,
            "flagged_events_per_minute": anomaly_count,
            "latest_event_age_ms": None if latest_event_ts is None else max(0, int((now - latest_event_ts) * 1000)),
            "latest_event_timestamp": latest_event_dt.isoformat() if latest_event_dt else None,
            "recent_buffered_events": len(events),
        }

    def get_open_fraud_alert_count(self) -> int:
        enable_session_rbac_override(self.db)
        return self.fraud_alert_repo.count_open_alerts()

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
        lag_ms = None
        operational_latest = self._ensure_aware(operational_latest)
        lakehouse_latest = self._ensure_aware(lakehouse_latest)
        if operational_latest and lakehouse_latest:
            delta_seconds = max(0.0, (operational_latest - lakehouse_latest).total_seconds())
            lag_seconds = int(delta_seconds)
            lag_ms = int(delta_seconds * 1000)

        return {
            "status": "SUCCESS" if not bq_error else "DEGRADED",
            "operational_latest_timestamp": operational_latest.isoformat() if operational_latest else None,
            "lakehouse_latest_timestamp": lakehouse_latest.isoformat() if lakehouse_latest else None,
            "replication_lag_seconds": lag_seconds,
            "replication_lag_ms": lag_ms,
            "lakehouse_row_count": lakehouse_count,
            "bigquery_dataset": self.lakehouse_repo.dataset,
            "bigquery_error": bq_error,
        }

    def get_cached_cdc_status(self) -> dict:
        global _cache
        if _cache:
            try:
                cached = _cache.get("cdc_status")
                if cached:
                    return json.loads(cached)
            except Exception as exc:
                logger.warning(f"Redis CDC status cache error: {exc}")

        status = self.get_cdc_status()
        if _cache:
            try:
                _cache.setex("cdc_status", 15, json.dumps(status))
            except Exception:
                pass
        return status

    def get_lakehouse_stream(self, limit: int = 20) -> dict:
        rows = self.lakehouse_repo.list_recent_transactions(limit=limit)
        return {
            "status": "SUCCESS",
            "stream": [self._format_stream_row(row) for row in rows],
        }

    def get_cached_datastream_metrics(self) -> dict:
        global _cache
        if _cache:
            try:
                cached = _cache.get("datastream_metrics")
                if cached:
                    metrics = json.loads(cached)
                    open_alerts = self.get_open_fraud_alert_count()
                    metrics["operational_active_fraud_alerts"] = open_alerts
                    metrics["active_anomalies"] = open_alerts
                    return metrics
            except Exception as exc:
                logger.warning(f"Redis cache error: {exc}")

        metrics = {
            "system_lag_ms": None,
            "data_freshness_ms": None,
            "total_bytes_processed": None,
            "active_anomalies": 0,
            "operational_active_fraud_alerts": 0,
            "lakehouse_fraud_anomalies": 0,
            "status": "SUCCESS",
        }

        try:
            metrics["operational_active_fraud_alerts"] = self.get_open_fraud_alert_count()
            metrics["active_anomalies"] = metrics["operational_active_fraud_alerts"]
        except Exception as exc:
            logger.warning(f"Error fetching operational fraud alert count: {exc}")
            metrics["status"] = "DEGRADED"

        try:
            metrics["lakehouse_fraud_anomalies"] = self.lakehouse_repo.get_anomalies_count()
        except Exception as exc:
            logger.warning(f"Error fetching anomalies count: {exc}")
            metrics["status"] = "DEGRADED"

        try:
            client = monitoring_v3.MetricServiceClient()
            project_name = f"projects/{self.project_id}"
            now = time.time()
            seconds = int(now)
            nanos = int((now - seconds) * 10**9)
            interval = monitoring_v3.TimeInterval(
                {
                    "end_time": {"seconds": seconds, "nanos": nanos},
                    "start_time": {"seconds": seconds - 300, "nanos": nanos},
                }
            )

            metric_types = [
                ("system_lag_ms", "datastream.googleapis.com/stream/system_latencies"),
                ("data_freshness_ms", "datastream.googleapis.com/stream/freshness"),
                ("total_bytes_processed", "datastream.googleapis.com/stream/bytes_count"),
            ]

            for key, metric_type in metric_types:
                results = client.list_time_series(
                    request={
                        "name": project_name,
                        "filter": f'metric.type = "{metric_type}"',
                        "interval": interval,
                    }
                )
                for result in results:
                    if not result.points:
                        continue
                    value = result.points[0].value
                    oneof_field = value._pb.WhichOneof("value")
                    if oneof_field == "int64_value":
                        metrics[key] = int(value.int64_value)
                    elif oneof_field == "double_value":
                        metrics[key] = int(round(value.double_value))
                    elif oneof_field == "distribution_value":
                        metrics[key] = int(round(value.distribution_value.mean))
                    break
        except Exception as exc:
            logger.warning(f"Error fetching cloud monitoring metrics: {exc}")
            metrics["status"] = "DEGRADED"

        if _cache:
            try:
                _cache.setex("datastream_metrics", 15, json.dumps(metrics))
            except Exception:
                pass

        return metrics
