-- BigQuery Active Lakehouse Pre-Canned View: v_international_fraud_anomalies
-- Isolates foreign card-present transactions where risk_score > 20 for Story 2 and Story 3
CREATE OR REPLACE VIEW `fsi_lakehouse.v_international_fraud_anomalies`
OPTIONS(
  description="International fraud anomaly isolation view for VIP Googlers and CE Presenters."
) AS
SELECT
  u.id AS user_id,
  CONCAT(u.first_name, ' ', u.last_name) AS cardholder_name,
  u.email,
  a.street_line_1,
  a.city AS home_metro,
  t.id AS authorization_id,
  t.merchant_name,
  t.transaction_amount_cents / 100.0 AS amount_dollars,
  s.country_code AS swipe_country,
  s.risk_score,
  t.created_at AS swipe_timestamp
FROM `fsi_lakehouse.cards_transaction_authorizations` t
JOIN `fsi_lakehouse.identity_users` u ON t.account_id = u.id
LEFT JOIN `fsi_lakehouse.identity_user_addresses` a ON u.id = a.user_id AND a.address_type = 'RESIDENTIAL'
JOIN `fsi_lakehouse.merchants_merchant_stores` s ON t.merchant_name = s.raw_descriptor
WHERE s.is_international = TRUE AND s.risk_score > 20
ORDER BY t.created_at DESC;
