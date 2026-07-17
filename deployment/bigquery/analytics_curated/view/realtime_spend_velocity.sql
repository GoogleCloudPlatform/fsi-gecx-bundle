CREATE OR REPLACE VIEW `__PROJECT_ID__.analytics_curated.realtime_spend_velocity` AS
SELECT
  merchant_category_code,
  card_network,
  COUNT(*) AS swipe_count,
  SUM(transaction_amount_cents) / 100.0 AS total_volume_dollars,
  AVG(transaction_amount_cents) / 100.0 AS avg_ticket_size_dollars,
  MAX(created_at) AS latest_swipe_timestamp
FROM `__PROJECT_ID__.oltp_cdc.cards_transaction_authorization`
WHERE status IN ('PENDING', 'APPROVED', 'SETTLED', 'FLAGGED')
GROUP BY merchant_category_code, card_network
ORDER BY latest_swipe_timestamp DESC
