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

import collections
import datetime
import json
import logging
import time

from google.cloud import monitoring_v3
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from models.credit_card import PostedTransaction, TransactionAuthorization
from models.fraud import FraudAlert, FraudModelDecision, ScenarioOutcome
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

    @staticmethod
    def _normalize_reason_code(reason: str | None) -> str:
        normalized = str(reason or "").upper()
        if "IMPOSSIBLE_TRAVEL" in normalized:
            return "Impossible Travel"
        if "FOREIGN" in normalized or "INTERNATIONAL" in normalized or "CROSS_BORDER" in normalized:
            return "Cross-Border Mismatch"
        if "CARD_NOT_PRESENT" in normalized or "CNP" in normalized:
            return "Card-Not-Present"
        if "DESCRIPTOR" in normalized or "MERCHANT_MISMATCH" in normalized:
            return "Merchant Descriptor Mismatch"
        if "VELOCITY" in normalized or "RAPID" in normalized:
            return "Velocity Spike"
        if "DIGITAL_GOODS" in normalized or "DIGITAL" in normalized:
            return "Digital Goods"
        if "GIFT_CARD" in normalized:
            return "Gift Card Purchase"
        if "FLAGGED_ACTIVITY" in normalized:
            return "Recent Flagged Activity"
        return str(reason or "Other").replace("_", " ").title()

    @staticmethod
    def _risk_state(score: int | None) -> str:
        if score is None:
            return "Not Scored"
        if score >= 90:
            return "Critical"
        if score >= 70:
            return "High"
        if score >= 25:
            return "Medium"
        return "Low"

    @staticmethod
    def _window_start(window_minutes: int) -> datetime.datetime:
        bounded = max(15, min(int(window_minutes or 15), 24 * 60))
        return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=bounded)

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

    def _list_window_authorizations(self, start_at: datetime.datetime, limit: int = 500):
        enable_session_rbac_override(self.db)
        return (
            self.db.query(TransactionAuthorization)
            .filter(TransactionAuthorization.created_at >= start_at)
            .order_by(desc(TransactionAuthorization.created_at))
            .limit(limit)
            .all()
        )

    def _list_window_posted_transactions(self, start_at: datetime.datetime, limit: int = 500):
        enable_session_rbac_override(self.db)
        return (
            self.db.query(PostedTransaction)
            .filter(PostedTransaction.posted_at >= start_at)
            .order_by(desc(PostedTransaction.posted_at))
            .limit(limit)
            .all()
        )

    def _list_window_decisions(self, start_at: datetime.datetime, limit: int = 1000):
        enable_session_rbac_override(self.db)
        return (
            self.db.query(FraudModelDecision)
            .filter(FraudModelDecision.created_at >= start_at)
            .order_by(desc(FraudModelDecision.created_at))
            .limit(limit)
            .all()
        )

    def _list_window_scenario_outcomes(self, start_at: datetime.datetime, limit: int = 500):
        enable_session_rbac_override(self.db)
        return (
            self.db.query(ScenarioOutcome)
            .filter(ScenarioOutcome.created_at >= start_at)
            .order_by(desc(ScenarioOutcome.created_at))
            .limit(limit)
            .all()
        )

    def _count_window_alerts(self, start_at: datetime.datetime) -> int:
        enable_session_rbac_override(self.db)
        return (
            self.db.query(FraudAlert)
            .filter(FraudAlert.created_at >= start_at)
            .count()
        )

    def _build_activity_series(
        self,
        *,
        window_minutes: int,
        authorizations: list[TransactionAuthorization],
        posted_transactions: list[PostedTransaction],
    ) -> list[dict]:
        bucket_count = 24
        now = datetime.datetime.now(datetime.timezone.utc)
        start_at = now - datetime.timedelta(minutes=window_minutes)
        bucket_seconds = max(60, int((window_minutes * 60) / bucket_count))
        buckets = [
            {
                "timestamp": (start_at + datetime.timedelta(seconds=bucket_seconds * index)).isoformat(),
                "events": 0,
                "authorizations": 0,
                "posted": 0,
                "flagged": 0,
            }
            for index in range(bucket_count)
        ]

        def bucket_index(value):
            value = self._ensure_aware(value)
            if not value:
                return None
            offset = max(0, int((value - start_at).total_seconds()))
            return min(bucket_count - 1, offset // bucket_seconds)

        for auth in authorizations:
            index = bucket_index(auth.created_at)
            if index is None:
                continue
            buckets[index]["events"] += 1
            buckets[index]["authorizations"] += 1
            if str(auth.status or "").upper() == "FLAGGED":
                buckets[index]["flagged"] += 1

        for posted in posted_transactions:
            index = bucket_index(posted.posted_at)
            if index is None:
                continue
            buckets[index]["events"] += 1
            buckets[index]["posted"] += 1

        return buckets

    def _format_monitor_transaction(
        self,
        *,
        event,
        event_type: str,
        decision_by_auth_id: dict[str, FraudModelDecision],
    ) -> dict:
        if event_type == "settlement":
            auth = event.authorization
            decision = None
            event_time = self._ensure_aware(event.posted_at)
            amount_cents = abs(event.amount_cents or 0)
            merchant_name = event.description
            status = "Posted"
            lifecycle = "Authorization → Settlement"
            account_id = str(event.account_id)
            rrn = event.retrieval_reference_number
            raw_descriptor = auth.merchant_name if auth else event.description
        else:
            decision = decision_by_auth_id.get(str(event.id))
            event_time = self._ensure_aware(event.created_at)
            amount_cents = abs(event.billing_amount_cents or event.transaction_amount_cents or 0)
            merchant_name = event.merchant_name
            status_text = str(event.status or "").upper()
            status = "Flagged" if status_text == "FLAGGED" else "Pending" if status_text == "PENDING" else "Failed" if status_text == "DECLINED" else "Pending"
            lifecycle = "Authorization → Review" if status == "Flagged" else "Authorization received"
            account_id = str(event.account_id)
            rrn = event.retrieval_reference_number
            raw_descriptor = event.merchant_name

        score = int(decision.score) if decision and decision.score is not None else None
        reasons = [
            self._normalize_reason_code(reason)
            for reason in (decision.reason_codes if decision else [])
            if str(reason).upper() not in {"BASELINE_LOW_RISK", "LOW_RISK"}
        ]
        return {
            "id": str(event.id),
            "event_type": event_type,
            "timestamp": event_time.isoformat() if event_time else None,
            "display_time": event_time.strftime("%H:%M:%S") if event_time else "N/A",
            "rrn": rrn,
            "account_suffix": account_id[-4:] if account_id else "N/A",
            "merchant_name": merchant_name,
            "raw_descriptor": raw_descriptor,
            "amount_cents": amount_cents,
            "risk_score": score,
            "risk_state": self._risk_state(score),
            "primary_finding": reasons[0] if reasons else "No finding",
            "signal_count": len(reasons),
            "status": status,
            "lifecycle": lifecycle,
            "latency_ms": None,
        }

    def get_operations_monitor_summary(self, window_minutes: int = 15) -> dict:
        window_minutes = max(15, min(int(window_minutes or 15), 24 * 60))
        start_at = self._window_start(window_minutes)
        datastream_metrics = self.get_cached_datastream_metrics()
        cdc_status = self.get_cached_cdc_status()

        authorizations = []
        posted_transactions = []
        decisions = []
        outcomes = []
        generated_alert_count = 0
        query_errors = []

        try:
            authorizations = self._list_window_authorizations(start_at)
        except Exception as exc:
            logger.warning("Unable to build windowed authorization summary: %s", exc)
            query_errors.append("authorizations")

        try:
            posted_transactions = self._list_window_posted_transactions(start_at)
        except Exception as exc:
            logger.warning("Unable to build windowed posted summary: %s", exc)
            query_errors.append("posted_transactions")

        try:
            decisions = self._list_window_decisions(start_at)
        except Exception as exc:
            logger.warning("Unable to build windowed fraud decision summary: %s", exc)
            query_errors.append("fraud_decisions")

        try:
            outcomes = self._list_window_scenario_outcomes(start_at)
        except Exception as exc:
            logger.warning("Unable to build windowed scenario outcome summary: %s", exc)
            query_errors.append("scenario_outcomes")

        try:
            generated_alert_count = self._count_window_alerts(start_at)
        except Exception as exc:
            logger.warning("Unable to build windowed alert summary: %s", exc)
            query_errors.append("fraud_alerts")

        decision_by_auth_id = {str(decision.authorization_id): decision for decision in decisions}
        high_risk_decisions = [decision for decision in decisions if int(decision.score or 0) >= 70]
        score_values = [int(decision.score) for decision in decisions if decision.score is not None]
        impacted_accounts = {
            str(auth.account_id)
            for auth in authorizations
            if getattr(auth, "account_id", None)
        } | {
            str(posted.account_id)
            for posted in posted_transactions
            if getattr(posted, "account_id", None)
        }
        pending_exposure_cents = sum(
            abs(auth.billing_amount_cents or auth.transaction_amount_cents or 0)
            for auth in authorizations
            if str(auth.status or "").upper() in {"PENDING", "FLAGGED"}
        )

        reason_counter = collections.Counter()
        risk_distribution = collections.Counter()
        for decision in decisions:
            risk_distribution[self._risk_state(int(decision.score) if decision.score is not None else None)] += 1
            for reason in decision.reason_codes or []:
                if str(reason).upper() in {"BASELINE_LOW_RISK", "LOW_RISK"}:
                    continue
                reason_counter[self._normalize_reason_code(reason)] += 1

        event_mix = {
            "authorization": len(authorizations),
            "settlement": len(posted_transactions),
            "flagged": sum(1 for auth in authorizations if str(auth.status or "").upper() == "FLAGGED"),
            "other": 0,
        }
        total_events = max(1, sum(event_mix.values()))
        event_mix_items = [
            {
                "label": label.replace("_", " ").title(),
                "count": count,
                "percentage": round((count / total_events) * 100),
            }
            for label, count in event_mix.items()
        ]

        scenario_counter = collections.defaultdict(lambda: {"events": 0, "high_risk": 0})
        for outcome in outcomes:
            scenario = str(outcome.scenario_id or "Synthetic Scenario").replace("_", " ").replace("-", " ").title()
            scenario_counter[scenario]["events"] += 1
            if int(outcome.actual_risk_score or 0) >= 70:
                scenario_counter[scenario]["high_risk"] += 1

        recent_events = []
        for auth in authorizations[:40]:
            recent_events.append(
                self._format_monitor_transaction(
                    event=auth,
                    event_type="authorization",
                    decision_by_auth_id=decision_by_auth_id,
                )
            )
        for posted in posted_transactions[:40]:
            recent_events.append(
                self._format_monitor_transaction(
                    event=posted,
                    event_type="settlement",
                    decision_by_auth_id=decision_by_auth_id,
                )
            )
        recent_events.sort(key=lambda event: event.get("timestamp") or "", reverse=True)

        stream_metrics = self.get_operational_stream_metrics()
        risk_total = max(1, sum(risk_distribution.values()))
        open_alerts = self.get_open_fraud_alert_count()
        return {
            "status": "DEGRADED" if query_errors else "SUCCESS",
            "window_minutes": window_minutes,
            "window_start": start_at.isoformat(),
            "query_errors": query_errors,
            "replication_health": {
                "stream_status": "LIVE",
                "latest_event_age_ms": stream_metrics.get("latest_event_age_ms"),
                "events_per_minute": stream_metrics.get("events_per_minute", 0),
                "replication_lag_ms": cdc_status.get("replication_lag_ms"),
                "data_freshness_ms": datastream_metrics.get("data_freshness_ms"),
                "system_lag_ms": datastream_metrics.get("system_lag_ms"),
                "error_rate": 0 if not query_errors else len(query_errors),
                "backlog_depth": stream_metrics.get("recent_buffered_events", 0),
            },
            "impact": {
                "open_fraud_alerts": open_alerts,
                "high_risk_transactions": len(high_risk_decisions),
                "accounts_impacted": len(impacted_accounts),
                "pending_exposure_cents": pending_exposure_cents,
                "active_scenarios": len(scenario_counter),
                "peak_risk_score": max(score_values) if score_values else None,
                "rules_triggered": len(reason_counter),
                "alerts_generated": generated_alert_count,
            },
            "event_mix": event_mix_items,
            "risk_distribution": [
                {
                    "label": label,
                    "count": risk_distribution.get(label, 0),
                    "percentage": round((risk_distribution.get(label, 0) / risk_total) * 100),
                }
                for label in ["Critical", "High", "Medium", "Low", "Not Scored"]
            ],
            "risk_signals": [
                {"label": label, "count": count}
                for label, count in reason_counter.most_common(5)
            ],
            "scenario_impact": [
                {
                    "label": label,
                    "events": values["events"],
                    "high_risk": values["high_risk"],
                }
                for label, values in sorted(
                    scenario_counter.items(),
                    key=lambda item: item[1]["events"],
                    reverse=True,
                )[:5]
            ],
            "activity_series": self._build_activity_series(
                window_minutes=window_minutes,
                authorizations=authorizations,
                posted_transactions=posted_transactions,
            ),
            "transactions": recent_events[:20],
            "system_health": [
                {"label": "Redis Cluster", "status": "Healthy", "detail": f"{stream_metrics.get('recent_buffered_events', 0)} buffered"},
                {"label": "PostgreSQL Outbox", "status": "Healthy", "detail": f"{len(authorizations) + len(posted_transactions)} window events"},
                {"label": "CDC Pipeline", "status": cdc_status.get("status", "SUCCESS"), "detail": f"Lag: {cdc_status.get('replication_lag_ms') or 0} ms"},
                {"label": "Analytics Datastore", "status": datastream_metrics.get("status", "SUCCESS"), "detail": f"Freshness: {datastream_metrics.get('data_freshness_ms') or 0} ms"},
                {"label": "Alerting Service", "status": "Healthy", "detail": f"Queue: {open_alerts}"},
                {"label": "Risk Engine", "status": "Healthy", "detail": f"Inferences: {len(decisions)}"},
            ],
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
