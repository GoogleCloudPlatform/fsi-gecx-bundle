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
from unittest.mock import patch

from services.cdc_monitoring import CdcMonitoringService


class FakeLakehouseRepository:
    dataset = "iceberg_catalog"

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
