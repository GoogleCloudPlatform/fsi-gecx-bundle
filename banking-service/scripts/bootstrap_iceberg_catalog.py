# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Idempotently creates the catalog-native Iceberg namespaces and V2 tables."""

from __future__ import annotations

import json
import os
from typing import Any

import google.auth
from google.auth.transport.requests import AuthorizedSession
from google.cloud import bigquery


REST_ROOT = "https://biglake.googleapis.com/iceberg/v1/restcatalog/v1"


AUDIT_FIELDS = [
    (1, "event_id", "string", True),
    (2, "event_type", "string", True),
    (3, "schema_version", "long", True),
    (4, "payload", "string", True),
    (5, "source_created_at", "timestamptz", True),
    (6, "published_at", "timestamptz", True),
    (7, "ingested_at", "timestamptz", True),
    (8, "transport_message_id", "string", False),
    (9, "transport_attributes", "string", False),
]

LEDGER_FIELDS = [
    (1, "entry_id", "string", True),
    (2, "event_id", "string", True),
    (3, "transaction_id", "string", True),
    (4, "account_id", "string", True),
    (5, "direction", "string", True),
    (6, "amount_cents", "long", True),
    (7, "currency", "string", True),
    (8, "source_type", "string", True),
    (9, "source_references", "string", False),
    (10, "posted_at", "timestamptz", True),
    (11, "source_created_at", "timestamptz", True),
    (12, "published_at", "timestamptz", True),
    (13, "ingested_at", "timestamptz", True),
]


def _view_queries(project_id: str, catalog_id: str) -> dict[str, str]:
    dataset = f"`{project_id}.compliance_audit"
    raw = f"`{project_id}.{catalog_id}.compliance_audit.audit_events`"
    ledger = f"`{project_id}.{catalog_id}.financial_ledger.account_ledger_entries`"
    return {
        "audit_events": f"""
          CREATE OR REPLACE VIEW {dataset}.audit_events` AS
          SELECT * EXCEPT (dedupe_ordinal)
          FROM (
            SELECT event_id, event_type, schema_version, payload,
                   source_created_at AS created_at, published_at, ingested_at,
                   transport_message_id, transport_attributes,
                   ROW_NUMBER() OVER (
                     PARTITION BY event_id
                     ORDER BY ingested_at DESC, published_at DESC, transport_message_id DESC
                   ) AS dedupe_ordinal
            FROM {raw}
          )
          WHERE dedupe_ordinal = 1
        """,
        "account_ledger_entries": f"""
          CREATE OR REPLACE VIEW {dataset}.account_ledger_entries` AS
          SELECT * EXCEPT (dedupe_ordinal)
          FROM (
            SELECT *, ROW_NUMBER() OVER (
              PARTITION BY entry_id ORDER BY ingested_at DESC, published_at DESC
            ) AS dedupe_ordinal
            FROM {ledger}
          )
          WHERE dedupe_ordinal = 1
        """,
        "account_ledger_balance": f"""
          CREATE OR REPLACE VIEW {dataset}.account_ledger_balance` AS
          SELECT transaction_id, currency,
                 SUM(IF(direction = 'DEBIT', amount_cents, 0)) AS debit_cents,
                 SUM(IF(direction = 'CREDIT', amount_cents, 0)) AS credit_cents,
                 SUM(IF(direction = 'DEBIT', amount_cents, -amount_cents)) AS imbalance_cents,
                 COUNT(*) AS entry_count
          FROM {dataset}.account_ledger_entries`
          GROUP BY transaction_id, currency
        """,
        "origination_audit_log": f"""
          CREATE OR REPLACE VIEW {dataset}.origination_audit_log` AS
          SELECT event_id, event_type,
                 JSON_VALUE(payload, '$.application_id') AS application_id,
                 JSON_VALUE(payload, '$.underwriter_id') AS underwriter_id,
                 payload, created_at
          FROM {dataset}.audit_events`
          WHERE event_type IN (
            'APPLICATION_CREATED', 'APPLICATION_SUBMITTED', 'APPLICATION_UPDATED',
            'ARTIFACT_UPLOADED', 'DOCUMENT_EXTRACTION_COMPLETED',
            'UNDERWRITING_OVERRIDE_APPLIED'
          )
        """,
        "financial_ledger_audit_log": f"""
          CREATE OR REPLACE VIEW {dataset}.financial_ledger_audit_log` AS
          SELECT event_id, event_type,
                 JSON_VALUE(payload, '$.account_id') AS account_id,
                 JSON_VALUE(payload, '$.transaction_id') AS transaction_id,
                 COALESCE(
                   CAST(JSON_VALUE(payload, '$.amount_cents') AS INT64),
                   (SELECT SUM(CAST(JSON_VALUE(entry, '$.amount_cents') AS INT64))
                    FROM UNNEST(JSON_QUERY_ARRAY(payload, '$.entries')) entry
                    WHERE JSON_VALUE(entry, '$.direction') = 'DEBIT')
                 ) AS amount_cents,
                 payload, created_at
          FROM {dataset}.audit_events`
          WHERE event_type IN (
            'FINANCIAL_TRANSACTION_POSTED', 'MONETARY_TRANSFER_EXECUTED',
            'CREDIT_LIMIT_INCREASED', 'FEE_REVERSED', 'CARD_FROZEN',
            'CREDIT_ACCOUNT_CREATED', 'CREDIT_CARD_ISSUED',
            'CREDIT_TRANSACTION_AUTHORIZED', 'CREDIT_TRANSACTION_SETTLED',
            'BILL_PAYMENT_EXECUTED'
          )
        """,
        "identity_access_audit_log": f"""
          CREATE OR REPLACE VIEW {dataset}.identity_access_audit_log` AS
          SELECT event_id, event_type, JSON_VALUE(payload, '$.user_id') AS user_id,
                 payload, created_at
          FROM {dataset}.audit_events`
          WHERE event_type IN (
            'USER_CREATED', 'USER_UPDATED', 'DEVICE_REGISTERED',
            'MESSAGE_SENT', 'KYC_RECORD_CREATED'
          )
        """,
        "system_config_audit_log": f"""
          CREATE OR REPLACE VIEW {dataset}.system_config_audit_log` AS
          SELECT event_id, event_type,
                 JSON_VALUE(payload, '$.product_code') AS product_code,
                 payload, created_at
          FROM {dataset}.audit_events`
          WHERE event_type IN (
            'CREDIT_PRODUCT_CATALOG_UPDATED', 'DEPOSIT_PRODUCT_CATALOG_UPDATED',
            'SYSTEM_FEATURE_FLAG_MODIFIED'
          )
        """,
    }


def reconcile_bigquery_views(client: Any, *, project_id: str, catalog_id: str) -> list[str]:
    """Creates logical deduplication and domain views after REST tables exist."""
    reconciled = []
    for name, query in _view_queries(project_id, catalog_id).items():
        client.query(query).result()
        reconciled.append(name)
    return reconciled


def _schema(fields: list[tuple[int, str, str, bool]]) -> dict[str, Any]:
    return {
        "type": "struct",
        "schema-id": 0,
        "identifier-field-ids": [],
        "fields": [
            {"id": field_id, "name": name, "required": required, "type": field_type}
            for field_id, name, field_type, required in fields
        ],
    }


class CatalogBootstrap:
    def __init__(self, session: Any, *, project_id: str, catalog_id: str, warehouse: str) -> None:
        self.session = session
        self.project_id = project_id
        self.catalog_id = catalog_id
        self.warehouse = warehouse.rstrip("/")
        self.base_url = f"{REST_ROOT}/projects/{project_id}/catalogs/{catalog_id}"
        self.headers = {
            "Content-Type": "application/json",
            "X-Goog-User-Project": project_id,
            "X-Iceberg-Access-Delegation": "vended-credentials",
        }

    def _post(self, url: str, body: dict[str, Any]) -> str:
        response = self.session.post(url, headers=self.headers, json=body, timeout=60)
        if response.status_code in {200, 201}:
            return "created"
        if response.status_code == 409:
            return "exists"
        raise RuntimeError(
            f"Lakehouse catalog request failed ({response.status_code}) {url}: {response.text}"
        )

    def ensure_namespace(self, namespace: str) -> str:
        return self._post(
            f"{self.base_url}/namespaces",
            {
                "namespace": [namespace],
                "properties": {"location": f"{self.warehouse}/{namespace}"},
            },
        )

    def ensure_table(
        self,
        namespace: str,
        table: str,
        fields: list[tuple[int, str, str, bool]],
    ) -> str:
        return self._post(
            f"{self.base_url}/namespaces/{namespace}/tables",
            {
                "name": table,
                "schema": _schema(fields),
                "partition-spec": {"spec-id": 0, "fields": []},
                "write-order": {"order-id": 0, "fields": []},
                "stage-create": False,
                "properties": {
                    "format-version": "2",
                    "write.format.default": "parquet",
                    "write.parquet.compression-codec": "zstd",
                },
            },
        )

    def run(self) -> dict[str, str]:
        result = {
            "compliance_audit_namespace": self.ensure_namespace("compliance_audit"),
            "financial_ledger_namespace": self.ensure_namespace("financial_ledger"),
        }
        result["audit_events_table"] = self.ensure_table(
            "compliance_audit", "audit_events", AUDIT_FIELDS
        )
        result["account_ledger_entries_table"] = self.ensure_table(
            "financial_ledger", "account_ledger_entries", LEDGER_FIELDS
        )
        return result


def main() -> None:
    project_id = os.environ["PROJECT_ID"]
    catalog_id = os.getenv("AUDIT_ICEBERG_CATALOG_ID", "nova-audit-lakehouse")
    warehouse = os.environ["AUDIT_ICEBERG_WAREHOUSE"]
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    session = AuthorizedSession(credentials)
    result = CatalogBootstrap(
        session,
        project_id=project_id,
        catalog_id=catalog_id,
        warehouse=warehouse,
    ).run()
    result["bigquery_views"] = reconcile_bigquery_views(
        bigquery.Client(project=project_id),
        project_id=project_id,
        catalog_id=catalog_id,
    )
    print(json.dumps({"status": "ok", "resources": result}, sort_keys=True))


if __name__ == "__main__":
    main()
