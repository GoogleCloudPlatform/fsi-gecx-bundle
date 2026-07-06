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
import os
import time
import json
import redis

from sqlalchemy import func
from sqlalchemy.orm import Session
from google.cloud import monitoring_v3

from models.credit_card import PostedTransaction, TransactionAuthorization
from repositories.cdc_lakehouse import CdcLakehouseRepository
from utils.gcp import get_project_id

logger = logging.getLogger(__name__)

def get_redis_client():
    redis_host = os.getenv("REDIS_HOST")
    redis_port = os.getenv("REDIS_PORT", "6379")
    redis_password = os.getenv("REDIS_PASSWORD")
    if not redis_host:
        return None
    try:
        return redis.Redis(
            host=redis_host, 
            port=int(redis_port), 
            password=redis_password,
            ssl=True,
            ssl_cert_reqs="none",
            decode_responses=True
        )
    except Exception as e:
        logger.warning(f"Failed to connect to redis: {e}")
        return None

_cache = get_redis_client()

class CdcMonitoringService:
    """Service layer for operational-to-lakehouse CDC monitoring."""

    def __init__(self, db: Session, lakehouse_repo: CdcLakehouseRepository | None = None):
        self.db = db
        self.lakehouse_repo = lakehouse_repo or CdcLakehouseRepository()
        self.project_id = get_project_id()

    @staticmethod
    def _ensure_aware(value):
        if value and value.tzinfo is None:
            return value.replace(tzinfo=datetime.timezone.utc)
        return value

    def get_operational_latest_timestamp(self):
        self.db.connection().info["_ignore_rbac"] = True
        latest_auth = self.db.query(func.max(TransactionAuthorization.created_at)).scalar()
        latest_posted = self.db.query(func.max(PostedTransaction.posted_at)).scalar()
        return max([dt for dt in [latest_auth, latest_posted] if dt], default=None)

    def get_cached_datastream_metrics(self) -> dict:
        global _cache
        if _cache:
            try:
                cached = _cache.get("datastream_metrics")
                if cached:
                    return json.loads(cached)
            except Exception as e:
                logger.warning(f"Redis cache error: {e}")

        metrics = {
            "system_lag": None,
            "data_freshness": None,
            "total_bytes_processed": None,
            "active_anomalies": 0,
            "status": "SUCCESS"
        }

        # Fetch active anomalies directly from BigQuery
        try:
            metrics["active_anomalies"] = self.lakehouse_repo.get_anomalies_count()
        except Exception as e:
            logger.warning(f"Error fetching anomalies count: {e}")
            metrics["status"] = "DEGRADED"

        # Fetch Cloud Monitoring metrics
        try:
            client = monitoring_v3.MetricServiceClient()
            project_name = f"projects/{self.project_id}"
            
            now = time.time()
            seconds = int(now)
            nanos = int((now - seconds) * 10 ** 9)
            # Look back up to 5 minutes to find the latest datapoint
            interval = monitoring_v3.TimeInterval({
                "end_time": {"seconds": seconds, "nanos": nanos},
                "start_time": {"seconds": seconds - 300, "nanos": nanos},
            })

            metric_types = [
                ("system_lag", "datastream.googleapis.com/stream/system_latencies"),
                ("data_freshness", "datastream.googleapis.com/stream/freshness"),
                ("total_bytes_processed", "datastream.googleapis.com/stream/bytes_count")
            ]
            
            for key, mtype in metric_types:
                results = client.list_time_series(request={
                    "name": project_name,
                    "filter": f'metric.type = "{mtype}"',
                    "interval": interval,
                })
                for result in results:
                    if result.points:
                        val = result.points[0].value
                        if val.HasField("int64_value"):
                            metrics[key] = val.int64_value
                        elif val.HasField("double_value"):
                            metrics[key] = val.double_value
                        break
        except Exception as e:
            logger.warning(f"Error fetching cloud monitoring metrics: {e}")
            metrics["status"] = "DEGRADED"

        if _cache:
            try:
                _cache.setex("datastream_metrics", 15, json.dumps(metrics))
            except Exception:
                pass

        return metrics

    def get_lakehouse_stream(self) -> dict:
        global _cache
        if _cache:
            try:
                cached = _cache.get("lakehouse_stream")
                if cached:
                    return json.loads(cached)
            except Exception:
                pass

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

        res = {"status": "SUCCESS", "stream": stream_items}
        if _cache:
            try:
                _cache.setex("lakehouse_stream", 15, json.dumps(res))
            except Exception:
                pass
        return res
