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

CREATE OR REPLACE VIEW `__PROJECT_ID__.analytics_curated.scenario_outcome_feedback` AS
SELECT
  CAST(NULL AS STRING) AS scenario_outcome_id,
  CAST(NULL AS STRING) AS scenario_id,
  CAST(NULL AS STRING) AS execution_id,
  CAST(NULL AS STRING) AS event_id,
  CAST(NULL AS STRING) AS authorization_id,
  CAST(NULL AS STRING) AS retrieval_reference_number,
  CAST(NULL AS STRING) AS transaction_id,
  CAST(NULL AS STRING) AS fraud_alert_id,
  CAST(NULL AS STRING) AS customer_id,
  CAST(NULL AS STRING) AS credit_account_id,
  CAST(NULL AS STRING) AS card_id,
  CAST(NULL AS STRING) AS card_token,
  CAST(NULL AS STRING) AS outcome_label,
  CAST(NULL AS BOOL) AS synthetic_label,
  CAST(NULL AS JSON) AS expected_reason_codes,
  CAST(NULL AS JSON) AS actual_reason_codes,
  CAST(NULL AS JSON) AS model_reason_codes,
  CAST(NULL AS STRING) AS expected_score_band,
  CAST(NULL AS INT64) AS actual_risk_score,
  CAST(NULL AS INT64) AS model_score,
  CAST(NULL AS INT64) AS model_threshold,
  CAST(NULL AS STRING) AS model_decision,
  CAST(NULL AS STRING) AS model_version,
  CAST(NULL AS STRING) AS operational_action,
  CAST(NULL AS STRING) AS operational_status,
  CAST(NULL AS STRING) AS merchant_name,
  CAST(NULL AS STRING) AS merchant_category_code,
  CAST(NULL AS FLOAT64) AS amount_dollars,
  CAST(NULL AS STRING) AS transaction_currency,
  CAST(NULL AS STRING) AS authorization_status,
  CAST(NULL AS TIMESTAMP) AS authorization_timestamp,
  CAST(NULL AS TIMESTAMP) AS decision_timestamp,
  CAST(NULL AS TIMESTAMP) AS outcome_timestamp
FROM UNNEST([1])
WHERE FALSE
