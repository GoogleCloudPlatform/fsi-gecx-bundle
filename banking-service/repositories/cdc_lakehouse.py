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
from typing import Any

from google.cloud import bigquery

from utils.gcp import get_project_id


class CdcLakehouseRepository:
    """Repository for BigQuery lakehouse CDC destination queries."""

    def __init__(self):
        self.project_id = get_project_id()
        self.dataset = os.getenv("CDC_BIGQUERY_DATASET", "iceberg_catalog")
        self.auth_table = os.getenv("CDC_BIGQUERY_AUTH_TABLE", "cards_transaction_authorization")
        self.posted_table = os.getenv("CDC_BIGQUERY_POSTED_TABLE", "cards_posted_transactions")
        self.curated_dataset = os.getenv("CDC_BIGQUERY_CURATED_DATASET", "analytics_curated")

    def _client(self):
        return bigquery.Client(project=self.project_id)

    @staticmethod
    def _row_to_dict(row) -> dict[str, Any]:
        return {key: row[key] for key in row.keys()}

    def _query(self, sql: str, limit: int = 20) -> list[dict[str, Any]]:
        query_job = self._client().query(sql)
        return [self._row_to_dict(row) for row in list(query_job.result(max_results=limit))]

    def get_cdc_watermark(self) -> dict[str, Any] | None:
        rows = self._query(f"""
            SELECT
              MAX(latest_ts) AS latest_ts,
              SUM(row_count) AS row_count
            FROM (
              SELECT MAX(created_at) AS latest_ts, COUNT(1) AS row_count
              FROM `{self.project_id}.{self.dataset}.{self.auth_table}`
              UNION ALL
              SELECT MAX(posted_at) AS latest_ts, COUNT(1) AS row_count
              FROM `{self.project_id}.{self.dataset}.{self.posted_table}`
            )
        """, limit=1)
        return rows[0] if rows else None

    def list_recent_transactions(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._query(f"""
            SELECT *
            FROM (
              SELECT
                CONCAT('BQ_AUTH_', SUBSTR(CAST(id AS STRING), 1, 8)) AS id,
                retrieval_reference_number AS rrn,
                created_at AS event_time,
                merchant_name,
                transaction_amount_cents AS amount_cents,
                CONCAT('HOLD (', status, ')') AS status,
                'lakehouse.transaction_authorization' AS source
              FROM `{self.project_id}.{self.dataset}.{self.auth_table}`
              UNION ALL
              SELECT
                CONCAT('BQ_POST_', SUBSTR(CAST(id AS STRING), 1, 8)) AS id,
                retrieval_reference_number AS rrn,
                posted_at AS event_time,
                description AS merchant_name,
                amount_cents,
                'SETTLE (POSTED)' AS status,
                'lakehouse.posted_transactions' AS source
              FROM `{self.project_id}.{self.dataset}.{self.posted_table}`
            )
            ORDER BY event_time DESC
            LIMIT {int(limit)}
        """, limit=limit)

    def get_anomalies_count(self) -> int:
        try:
            rows = self._query(f"""
                SELECT COUNT(1) AS cnt
                FROM `{self.project_id}.{self.curated_dataset}.international_fraud_anomalies`
            """, limit=1)
            return int(rows[0]["cnt"]) if rows else 0
        except Exception:
            return 0
