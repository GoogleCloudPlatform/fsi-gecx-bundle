CREATE OR REPLACE VIEW `__PROJECT_ID__.analytics_curated.scenario_outcome_feedback` AS
WITH outcomes AS (
  SELECT
    id AS scenario_outcome_id,
    scenario_id,
    execution_id,
    event_id,
    authorization_id,
    transaction_id,
    fraud_alert_id,
    customer_id,
    credit_account_id,
    card_id,
    card_token,
    outcome_label,
    expected_reason_codes,
    actual_reason_codes,
    expected_score_band,
    actual_risk_score,
    model_version,
    synthetic_label,
    operational_action,
    operational_status,
    created_at AS outcome_timestamp
  FROM `__PROJECT_ID__.iceberg_catalog.operations_scenario_outcomes`
),
decisions AS (
  SELECT
    authorization_id,
    score AS model_score,
    threshold AS model_threshold,
    decision AS model_decision,
    reason_codes AS model_reason_codes,
    model_version,
    created_at AS decision_timestamp
  FROM `__PROJECT_ID__.iceberg_catalog.operations_fraud_model_decisions`
),
authorizations AS (
  SELECT
    id AS authorization_id,
    retrieval_reference_number,
    merchant_name,
    merchant_category_code,
    transaction_amount_cents / 100.0 AS amount_dollars,
    transaction_currency,
    status AS authorization_status,
    created_at AS authorization_timestamp
  FROM `__PROJECT_ID__.iceberg_catalog.cards_transaction_authorization`
)
SELECT
  o.scenario_outcome_id,
  o.scenario_id,
  o.execution_id,
  o.event_id,
  o.authorization_id,
  a.retrieval_reference_number,
  o.transaction_id,
  o.fraud_alert_id,
  o.customer_id,
  o.credit_account_id,
  o.card_id,
  o.card_token,
  o.outcome_label,
  o.synthetic_label,
  o.expected_reason_codes,
  o.actual_reason_codes,
  d.model_reason_codes,
  o.expected_score_band,
  o.actual_risk_score,
  d.model_score,
  d.model_threshold,
  d.model_decision,
  COALESCE(o.model_version, d.model_version) AS model_version,
  o.operational_action,
  o.operational_status,
  a.merchant_name,
  a.merchant_category_code,
  a.amount_dollars,
  a.transaction_currency,
  a.authorization_status,
  a.authorization_timestamp,
  d.decision_timestamp,
  o.outcome_timestamp
FROM outcomes o
LEFT JOIN decisions d
  ON d.authorization_id = o.authorization_id
LEFT JOIN authorizations a
  ON a.authorization_id = o.authorization_id
ORDER BY o.outcome_timestamp DESC
