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
