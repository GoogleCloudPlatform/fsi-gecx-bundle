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
from types import SimpleNamespace
from unittest.mock import patch

from services.cdc_monitoring import CdcMonitoringService


class FakeLakehouseRepository:
    dataset = "oltp_cdc"

    def __init__(self, watermark=None, rows=None, error=None, anomalies_count=0):
        self.watermark = watermark
        self.rows = rows or []
        self.error = error
        self.anomalies_count = anomalies_count

    def get_cdc_watermark(self):
        if self.error:
            raise self.error
        return self.watermark

    def list_recent_transactions(self, limit=20):
        if self.error:
            raise self.error
        return self.rows[:limit]

    def get_anomalies_count(self):
        if self.error:
            raise self.error
        return self.anomalies_count

class FakeSession:
    def __init__(self, open_fraud_alert_count=0):
        self.open_fraud_alert_count = open_fraud_alert_count

    def query(self, *_args, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def count(self):
        return self.open_fraud_alert_count

    def scalar(self):
        return datetime.datetime(2026, 7, 6, 12, 0, 5, tzinfo=datetime.timezone.utc)

    def connection(self):
        class FakeConnection:
            info = {}
        return FakeConnection()


def test_cdc_status_calculates_lag():
    repo = FakeLakehouseRepository(
        watermark={
            "latest_ts": datetime.datetime(2026, 7, 6, 12, 0, 0, tzinfo=datetime.timezone.utc),
            "row_count": 42,
        }
    )
    service = CdcMonitoringService(FakeSession(), repo)

    result = service.get_cdc_status()

    assert result["status"] == "SUCCESS"
    assert result["replication_lag_seconds"] == 5
    assert result["lakehouse_row_count"] == 42


def test_cdc_status_reports_degraded_on_bigquery_error():
    service = CdcMonitoringService(FakeSession(), FakeLakehouseRepository(error=RuntimeError("bq down")))

    result = service.get_cdc_status()

    assert result["status"] == "DEGRADED"
    assert result["bigquery_error"] == "bq down"


def test_cached_cdc_status_uses_redis_snapshot():
    service = CdcMonitoringService(FakeSession(), FakeLakehouseRepository(error=RuntimeError("should not query")))
    cached_status = {
        "status": "SUCCESS",
        "operational_latest_timestamp": "2026-07-06T12:00:05+00:00",
        "lakehouse_latest_timestamp": "2026-07-06T12:00:00+00:00",
        "replication_lag_seconds": 5,
        "replication_lag_ms": 5000,
        "lakehouse_row_count": 42,
        "bigquery_dataset": "oltp_cdc",
        "bigquery_error": None,
    }

    class FakeCache:
        def get(self, key):
            assert key == "cdc_status"
            import json
            return json.dumps(cached_status)

    with patch("services.cdc_monitoring._cache", FakeCache()):
        result = service.get_cached_cdc_status()

    assert result == cached_status


def test_lakehouse_stream_normalizes_rows():
    event_time = datetime.datetime(2026, 7, 6, 12, 0, 0, tzinfo=datetime.timezone.utc)
    repo = FakeLakehouseRepository(rows=[{
        "id": "BQ_AUTH_12345678",
        "rrn": "123",
        "event_time": event_time,
        "merchant_name": "TEST MERCHANT",
        "amount_cents": 1200,
        "status": "HOLD (PENDING)",
        "source": "lakehouse.transaction_authorization",
    }])
    service = CdcMonitoringService(FakeSession(), repo)

    result = service.get_lakehouse_stream()

    assert result["status"] == "SUCCESS"
    assert result["stream"][0]["timestamp"] == "12:00:00"
    assert result["stream"][0]["bq_view"] == "lakehouse.transaction_authorization"


def test_operational_stream_metrics_derive_event_rate():
    service = CdcMonitoringService(FakeSession(), FakeLakehouseRepository())
    now = datetime.datetime(2026, 7, 6, 12, 0, 0, tzinfo=datetime.timezone.utc).timestamp()

    with patch.object(
        service,
        "_get_recent_operational_events",
        return_value=[
            {"status": "HOLD (PENDING)", "raw_time": now - 4},
            {"status": "SETTLE (POSTED)", "raw_time": now - 2},
            {"status": "FLAGGED (RISK 30)", "raw_time": now - 1},
        ],
    ), patch("services.cdc_monitoring.time.time", return_value=now):
        result = service.get_operational_stream_metrics()

    assert result["events_per_minute"] == 3
    assert result["authorization_events_per_minute"] == 2
    assert result["posted_events_per_minute"] == 1
    assert result["flagged_events_per_minute"] == 1
    assert result["latest_event_age_ms"] == 1000


def test_datastream_metrics_keep_operational_fraud_alert_floor():
    service = CdcMonitoringService(
        FakeSession(open_fraud_alert_count=2),
        FakeLakehouseRepository(anomalies_count=0),
    )

    with patch("services.cdc_monitoring._cache", None), \
         patch("services.cdc_monitoring.monitoring_v3.MetricServiceClient") as mock_client:
        mock_client.return_value.list_time_series.return_value = []
        result = service.get_cached_datastream_metrics()

    assert result["operational_active_fraud_alerts"] == 2
    assert result["active_anomalies"] == 2


def test_datastream_metrics_do_not_treat_historical_lakehouse_rows_as_active():
    service = CdcMonitoringService(
        FakeSession(open_fraud_alert_count=0),
        FakeLakehouseRepository(anomalies_count=3),
    )

    with patch("services.cdc_monitoring._cache", None), \
         patch("services.cdc_monitoring.monitoring_v3.MetricServiceClient") as mock_client:
        mock_client.return_value.list_time_series.return_value = []
        result = service.get_cached_datastream_metrics()

    assert result["operational_active_fraud_alerts"] == 0
    assert result["lakehouse_fraud_anomalies"] == 3
    assert result["active_anomalies"] == 0


def test_operations_monitor_summary_builds_windowed_operational_view():
    now = datetime.datetime(2026, 7, 6, 12, 0, 0, tzinfo=datetime.timezone.utc)
    auth = SimpleNamespace(
        id="auth-1",
        account_id="account-12345678",
        created_at=now - datetime.timedelta(minutes=2),
        billing_amount_cents=84220,
        transaction_amount_cents=84220,
        merchant_name="El Palacio de Hierro",
        status="FLAGGED",
        retrieval_reference_number="695818055522",
    )
    posted = SimpleNamespace(
        id="posted-1",
        authorization=auth,
        authorization_id="auth-1",
        account_id="account-12345678",
        posted_at=now - datetime.timedelta(minutes=1),
        amount_cents=-84220,
        description="EL PALACIO DE HIERRO PO",
        retrieval_reference_number="261271627828",
    )
    decision = SimpleNamespace(
        authorization_id="auth-1",
        score=87,
        reason_codes=["IMPOSSIBLE_TRAVEL", "CROSS_BORDER_ANOMALY", "BASELINE_LOW_RISK"],
        created_at=now - datetime.timedelta(minutes=2),
    )
    outcome = SimpleNamespace(
        scenario_id="impossible_travel_campaign",
        actual_risk_score=87,
        created_at=now - datetime.timedelta(minutes=2),
    )
    service = CdcMonitoringService(FakeSession(), FakeLakehouseRepository())

    with patch("services.cdc_monitoring.datetime") as mock_datetime, \
         patch.object(service, "_list_window_authorizations", return_value=[auth]), \
         patch.object(service, "_list_window_posted_transactions", return_value=[posted]), \
         patch.object(service, "_list_window_decisions", return_value=[decision]), \
         patch.object(service, "_list_window_scenario_outcomes", return_value=[outcome]), \
         patch.object(service, "_count_window_alerts", return_value=1), \
         patch.object(service, "get_open_fraud_alert_count", return_value=3), \
         patch.object(service, "get_cached_datastream_metrics", return_value={"status": "SUCCESS", "data_freshness_ms": 12, "system_lag_ms": 3}), \
         patch.object(service, "get_cached_cdc_status", return_value={"status": "SUCCESS", "replication_lag_ms": 42}), \
         patch.object(service, "get_operational_stream_metrics", return_value={"latest_event_age_ms": 31, "events_per_minute": 128, "recent_buffered_events": 186}):
        mock_datetime.datetime.now.return_value = now
        mock_datetime.datetime.fromtimestamp = datetime.datetime.fromtimestamp
        mock_datetime.datetime.side_effect = lambda *args, **kwargs: datetime.datetime(*args, **kwargs)
        mock_datetime.timedelta = datetime.timedelta
        mock_datetime.timezone = datetime.timezone

        result = service.get_operations_monitor_summary(window_minutes=15)

    assert result["status"] == "SUCCESS"
    assert result["replication_health"]["events_per_minute"] == 128
    assert result["impact"]["open_fraud_alerts"] == 3
    assert result["impact"]["high_risk_transactions"] == 1
    assert result["impact"]["accounts_impacted"] == 1
    assert result["impact"]["pending_exposure_cents"] == 84220
    assert result["risk_signals"] == [
        {"label": "Impossible Travel", "count": 1},
        {"label": "Cross-Border Mismatch", "count": 1},
    ]
    assert {"label": "High", "count": 1, "percentage": 100} in result["risk_distribution"]
    assert result["event_mix"][0]["label"] == "Authorization"
    assert len(result["activity_series"]) == 15
    assert result["activity_series"][-1]["timestamp"] == (now - datetime.timedelta(minutes=1)).isoformat()
    assert result["scenario_impact"][0] == {
        "label": "Impossible Travel Campaign",
        "events": 1,
        "high_risk": 1,
    }
    settlement_row = next(item for item in result["transactions"] if item["event_type"] == "settlement")
    auth_row = next(item for item in result["transactions"] if item["event_type"] == "authorization")
    assert settlement_row["risk_state"] == "Not Scored"
    assert settlement_row["risk_score"] is None
    assert auth_row["risk_state"] == "High"
    assert auth_row["risk_score"] == 87
