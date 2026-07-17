CREATE OR REPLACE VIEW `__PROJECT_ID__.analytics_curated.international_fraud_anomalies` AS
SELECT
  id AS authorization_id,
  account_id,
  card_id,
  merchant_name,
  merchant_category_code,
  transaction_amount_cents / 100.0 AS amount_dollars,
  transaction_currency,
  billing_currency,
  card_network,
  fraud_risk_score,
  status,
  created_at AS swipe_timestamp
FROM `__PROJECT_ID__.oltp_cdc.cards_transaction_authorization`
WHERE COALESCE(fraud_risk_score, 0) > 20
   OR status = 'FLAGGED'
ORDER BY created_at DESC
