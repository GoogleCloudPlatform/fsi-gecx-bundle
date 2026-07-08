CREATE OR REPLACE VIEW `__PROJECT_ID__.analytics_curated.enriched_posted_transactions` AS
SELECT
  pt.id AS transaction_id,
  pt.account_id,
  c.id AS card_id,
  c.last_four AS card_last_four,
  c.is_active AS card_is_active,
  pt.amount_cents,
  auth.merchant_name,
  auth.merchant_category_code,
  auth.card_network,
  auth.fraud_risk_score,
  pt.description,
  pt.posted_at,
  auth.status AS authorization_status,
  auth.decline_reason
FROM `__PROJECT_ID__.iceberg_catalog.cards_posted_transactions` pt
LEFT JOIN `__PROJECT_ID__.iceberg_catalog.cards_transaction_authorization` auth
  ON pt.authorization_id = auth.id
LEFT JOIN `__PROJECT_ID__.iceberg_catalog.cards_issued_card` c
  ON auth.card_id = c.id
