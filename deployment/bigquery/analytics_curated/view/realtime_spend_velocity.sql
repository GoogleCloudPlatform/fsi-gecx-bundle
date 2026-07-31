-- Copyright 2026 Google LLC
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--     https://www.apache.org/licenses/LICENSE-2.0
--
-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.

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
