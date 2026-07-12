CREATE OR REPLACE VIEW `__PROJECT_ID__.analytics_curated.fraud_model_decision_history` AS
WITH decisions AS (
  SELECT
    id AS fraud_decision_id,
    authorization_id,
    customer_id,
    credit_account_id,
    card_id,
    score,
    threshold,
    decision,
    reason_codes,
    feature_snapshot,
    merchant_name AS decision_merchant_name,
    merchant_category_code AS decision_mcc,
    transaction_channel,
    merchant_country_code,
    merchant_city,
    merchant_region,
    model_version,
    created_at AS decision_timestamp
  FROM `__PROJECT_ID__.iceberg_catalog.operations_fraud_model_decisions`
),
authorizations AS (
  SELECT
    id AS authorization_id,
    retrieval_reference_number,
    merchant_name AS authorization_merchant_name,
    merchant_category_code AS authorization_mcc,
    transaction_amount_cents,
    transaction_currency,
    fraud_risk_score,
    status AS authorization_status,
    merchant_latitude AS authorization_merchant_latitude,
    merchant_longitude AS authorization_merchant_longitude,
    created_at AS authorization_timestamp
  FROM `__PROJECT_ID__.iceberg_catalog.cards_transaction_authorization`
)
SELECT
  d.fraud_decision_id,
  d.authorization_id,
  a.retrieval_reference_number,
  d.customer_id,
  d.credit_account_id,
  d.card_id,
  d.score,
  d.threshold,
  d.decision,
  d.reason_codes,
  ARRAY_TO_STRING(
    ARRAY(
      SELECT REPLACE(reason_code, '_', ' ')
      FROM UNNEST(IFNULL(JSON_VALUE_ARRAY(d.reason_codes), [])) AS reason_code
      LIMIT 3
    ),
    ', '
  ) AS reason_summary,
  d.feature_snapshot,
  JSON_VALUE(d.feature_snapshot, '$.mcc_primary_category') AS mcc_primary_category,
  JSON_VALUE(d.feature_snapshot, '$.mcc_detailed_category') AS mcc_detailed_category,
  JSON_VALUE(d.feature_snapshot, '$.mcc_risk_level') AS mcc_risk_level,
  SAFE_CAST(JSON_VALUE(d.feature_snapshot, '$.mcc_risk_score') AS INT64) AS mcc_risk_score,
  JSON_VALUE(d.feature_snapshot, '$.mcc_velocity_risk') AS mcc_velocity_risk,
  SAFE_CAST(JSON_VALUE(d.feature_snapshot, '$.mcc_chargeback_prone') AS BOOL) AS mcc_chargeback_prone,
  JSON_VALUE_ARRAY(d.feature_snapshot, '$.mcc_risk_flags') AS mcc_risk_flags,
  SAFE_CAST(JSON_VALUE(d.feature_snapshot, '$.merchant_intelligence_matched') AS BOOL) AS merchant_intelligence_matched,
  JSON_VALUE(d.feature_snapshot, '$.normalized_merchant') AS normalized_merchant,
  JSON_VALUE(d.feature_snapshot, '$.merchant_type') AS merchant_type,
  SAFE_CAST(JSON_VALUE(d.feature_snapshot, '$.merchant_intelligence_risk_score') AS INT64) AS merchant_intelligence_risk_score,
  JSON_VALUE_ARRAY(d.feature_snapshot, '$.merchant_intelligence_flags') AS merchant_intelligence_flags,
  JSON_VALUE(d.feature_snapshot, '$.merchant_intelligence_match_type') AS merchant_intelligence_match_type,
  SAFE_CAST(JSON_VALUE(d.feature_snapshot, '$.merchant_intelligence_mcc_match') AS BOOL) AS merchant_intelligence_mcc_match,
  d.model_version,
  COALESCE(d.decision_merchant_name, a.authorization_merchant_name) AS merchant_name,
  COALESCE(d.decision_mcc, a.authorization_mcc) AS merchant_category_code,
  d.transaction_channel,
  d.merchant_country_code,
  d.merchant_city,
  d.merchant_region,
  COALESCE(
    SAFE_CAST(JSON_VALUE(d.feature_snapshot, '$.merchant_latitude') AS NUMERIC),
    a.authorization_merchant_latitude
  ) AS merchant_latitude,
  COALESCE(
    SAFE_CAST(JSON_VALUE(d.feature_snapshot, '$.merchant_longitude') AS NUMERIC),
    a.authorization_merchant_longitude
  ) AS merchant_longitude,
  a.transaction_amount_cents / 100.0 AS amount_dollars,
  a.transaction_currency,
  a.fraud_risk_score,
  a.authorization_status,
  a.authorization_timestamp,
  d.decision_timestamp,
  TIMESTAMP_DIFF(d.decision_timestamp, a.authorization_timestamp, SECOND) AS authorization_to_decision_seconds
FROM decisions d
LEFT JOIN authorizations a
  ON a.authorization_id = d.authorization_id
ORDER BY d.decision_timestamp DESC
