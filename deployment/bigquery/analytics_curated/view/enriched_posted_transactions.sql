CREATE OR REPLACE VIEW `__PROJECT_ID__.analytics_curated.enriched_posted_transactions` AS
SELECT
  pt.id AS transaction_id,
  pt.account_id,
  account.customer_id,
  c.id AS card_id,
  c.last_four AS card_last_four,
  c.is_active AS card_is_active,
  pt.amount_cents,
  pt.amount_cents / 100.0 AS signed_amount_dollars,
  IF(pt.amount_cents < 0, ABS(pt.amount_cents) / 100.0, 0) AS spend_amount_dollars,
  pt.amount_cents < 0 AS is_spend,
  auth.merchant_name,
  auth.merchant_category_code,
  auth.merchant_id,
  auth.merchant_store_id,
  auth.merchant_city,
  auth.merchant_region,
  COALESCE(auth.merchant_country_code, auth.shipping_country_code)
    AS merchant_country_code,
  auth.card_network,
  auth.fraud_risk_score,
  auth.transaction_currency,
  auth.transaction_channel,
  pt.description,
  pt.posted_at,
  auth.status AS authorization_status,
  auth.decline_reason
FROM `__PROJECT_ID__.oltp_cdc.cards_posted_transactions` pt
LEFT JOIN `__PROJECT_ID__.oltp_cdc.cards_transaction_authorization` auth
  ON pt.authorization_id = auth.id
LEFT JOIN `__PROJECT_ID__.oltp_cdc.cards_issued_card` c
  ON auth.card_id = c.id
LEFT JOIN `__PROJECT_ID__.oltp_cdc.cards_credit_accounts` account
  ON pt.account_id = account.id
