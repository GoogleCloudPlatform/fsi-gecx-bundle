-- BigQuery Active Lakehouse Pre-Canned View: v_realtime_spend_velocity
-- Aggregates CDC transaction volume and ticket size by FDX spend category and home metro
CREATE OR REPLACE VIEW `fsi_lakehouse.v_realtime_spend_velocity`
OPTIONS(
  description="Real-time CDC spend velocity aggregation for BigQuery Data Canvas and Looker semantic models."
) AS
SELECT
  a.city AS home_metro,
  m.category AS spend_category,
  COUNT(t.id) AS swipe_count,
  SUM(t.transaction_amount_cents) / 100.0 AS total_volume_dollars,
  AVG(t.transaction_amount_cents) / 100.0 AS avg_ticket_size_dollars,
  MAX(t.created_at) AS latest_swipe_timestamp
FROM `fsi_lakehouse.cards_transaction_authorizations` t
JOIN `fsi_lakehouse.cards_credit_accounts` c ON t.account_id = c.id
JOIN `fsi_lakehouse.identity_users` u ON c.customer_id = u.id
LEFT JOIN `fsi_lakehouse.identity_user_addresses` a ON u.id = a.user_id AND a.address_type = 'RESIDENTIAL'
LEFT JOIN `fsi_lakehouse.ref_data_merchant_master` m ON t.merchant_category_code = m.mcc
WHERE t.status = 'PENDING'
GROUP BY 1, 2
ORDER BY swipe_count DESC;
