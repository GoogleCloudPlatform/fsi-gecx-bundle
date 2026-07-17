CREATE OR REPLACE VIEW `__PROJECT_ID__.analytics_curated.premium_travel_offer_candidates` AS
WITH enriched_authorizations AS (
  SELECT
    auth.id AS authorization_id,
    auth.created_at AS swipe_timestamp,
    auth.transaction_amount_cents,
    auth.status AS authorization_status,
    auth.merchant_name,
    auth.merchant_category_code,
    auth.card_network,
    card.id AS card_id,
    card.last_four AS card_last_four,
    card.status AS card_status,
    card.is_active AS card_is_active,
    account.id AS credit_account_id,
    account.customer_id,
    account.status AS credit_account_status,
    account.credit_limit_cents,
    user.first_name,
    user.last_name,
    user.email,
    address.city,
    address.state,
    auth.merchant_country_code AS destination_country_code,
    0 AS merchant_risk_score,
    CASE
      WHEN auth.merchant_category_code IN ('4511') THEN 'TRAVEL'
      WHEN auth.merchant_category_code IN ('7011') THEN 'TRAVEL'
      WHEN auth.merchant_category_code IN ('5812', '5814') THEN 'DINING'
      WHEN auth.merchant_category_code IN ('7298') THEN 'PERSONAL_SERVICES'
      WHEN auth.merchant_category_code IN ('4121') THEN 'TRANSPORTATION'
      WHEN auth.merchant_category_code IN ('3351', '3355', '3366', '3389') THEN 'TRAVEL'
      ELSE 'OTHER'
    END AS merchant_primary_category,
    CASE
      WHEN auth.merchant_category_code IN ('4511') THEN 'Airlines'
      WHEN auth.merchant_category_code IN ('7011') THEN 'Hotels and resorts'
      WHEN auth.merchant_category_code IN ('5812', '5814') THEN 'Dining'
      WHEN auth.merchant_category_code IN ('7298') THEN 'Spa and wellness'
      WHEN auth.merchant_category_code IN ('4121') THEN 'Ground transportation'
      WHEN auth.merchant_category_code IN ('3351', '3355', '3366', '3389') THEN 'Car rental'
      ELSE 'Other merchant'
    END AS merchant_detailed_category,
    auth.merchant_name AS normalized_merchant_name,
    CASE
      WHEN auth.merchant_category_code IN ('4511') THEN 'AIRLINE'
      WHEN auth.merchant_category_code IN ('7011') THEN 'LODGING'
      WHEN auth.merchant_category_code IN ('5812', '5814') THEN 'DINING'
      WHEN auth.merchant_category_code IN ('7298') THEN 'WELLNESS'
      WHEN auth.merchant_category_code IN ('4121') THEN 'GROUND_TRANSPORTATION'
      WHEN auth.merchant_category_code IN ('3351', '3355', '3366', '3389') THEN 'CAR_RENTAL'
      ELSE 'OTHER'
    END AS travel_category,
    CASE
      WHEN UPPER(address.city) IN ('MOUNTAIN VIEW', 'PALO ALTO', 'LOS ALTOS', 'LOS ALTOS HILLS', 'MENLO PARK', 'WOODSIDE', 'ATHERTON', 'PORTOLA VALLEY', 'HILLSBOROUGH', 'SARATOGA')
        AND UPPER(address.state) = 'CA'
        THEN 'MOUNTAIN VIEW CA'
      WHEN UPPER(address.city) = 'SAN FRANCISCO' AND UPPER(address.state) = 'CA'
        THEN 'SAN FRANCISCO CA'
      WHEN UPPER(address.state) = 'CA'
        THEN CONCAT(UPPER(address.city), ' CA')
      ELSE CONCAT(UPPER(address.city), ' ', UPPER(address.state))
    END AS home_metro
  FROM `__PROJECT_ID__.oltp_cdc.cards_transaction_authorization` auth
  JOIN `__PROJECT_ID__.oltp_cdc.cards_issued_card` card
    ON auth.card_id = card.id
  JOIN `__PROJECT_ID__.oltp_cdc.cards_credit_accounts` account
    ON card.account_id = account.id
  JOIN `__PROJECT_ID__.oltp_cdc.identity_users` user
    ON account.customer_id = user.id
  LEFT JOIN `__PROJECT_ID__.oltp_cdc.identity_user_addresses` address
    ON user.id = address.user_id
   AND address.is_primary = TRUE
  WHERE auth.status IN ('PENDING', 'APPROVED', 'SETTLED', 'FLAGGED')
    AND auth.created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
),
travel_activity AS (
  SELECT *
  FROM enriched_authorizations
  WHERE destination_country_code != 'USA'
     OR merchant_category_code IN ('4511', '7011', '5812', '5814', '7298', '4121', '3351', '3355', '3366', '3389')
),
candidate_rollup AS (
  SELECT
    customer_id,
    CONCAT(first_name, ' ', last_name) AS customer_name,
    email,
    home_metro,
    city,
    state,
    card_id,
    card_last_four,
    card_status,
    card_is_active,
    credit_account_id,
    credit_account_status,
    credit_limit_cents,
    destination_country_code,
    CASE
      WHEN destination_country_code = 'MEX' THEN 'Mexico'
      WHEN destination_country_code = 'USA' THEN 'United States'
      ELSE destination_country_code
    END AS destination_country_name,
    SUM(transaction_amount_cents) / 100.0 AS recent_travel_spend_dollars,
    SUM(IF(destination_country_code = 'MEX', transaction_amount_cents, 0)) / 100.0 AS recent_mexico_spend_dollars,
    COUNT(*) AS travel_transaction_count,
    COUNT(DISTINCT travel_category) AS travel_category_count,
    STRING_AGG(DISTINCT travel_category, ', ' ORDER BY travel_category LIMIT 6) AS top_merchant_categories,
    STRING_AGG(DISTINCT normalized_merchant_name, ', ' ORDER BY normalized_merchant_name LIMIT 5) AS sample_merchants,
    MAX(swipe_timestamp) AS latest_travel_swipe_at,
    MAX(merchant_risk_score) AS max_merchant_risk_score
  FROM travel_activity
  GROUP BY
    customer_id,
    customer_name,
    email,
    home_metro,
    city,
    state,
    card_id,
    card_last_four,
    card_status,
    card_is_active,
    credit_account_id,
    credit_account_status,
    credit_limit_cents,
    destination_country_code,
    destination_country_name
)
SELECT
  customer_id,
  customer_name,
  email,
  home_metro,
  city,
  state,
  card_id,
  card_last_four,
  card_status,
  card_is_active,
  credit_account_id,
  credit_account_status,
  credit_limit_cents,
  destination_country_code,
  destination_country_name,
  recent_travel_spend_dollars,
  recent_mexico_spend_dollars,
  travel_transaction_count,
  travel_category_count,
  top_merchant_categories,
  sample_merchants,
  latest_travel_swipe_at,
  max_merchant_risk_score,
  'Premium Travel Rewards Card' AS recommended_offer,
  CASE
    WHEN destination_country_code = 'MEX'
      AND recent_mexico_spend_dollars > 0
      AND travel_category_count >= 3
      THEN CONCAT('Recent Mexico spend across ', CAST(travel_category_count AS STRING), ' travel categories suggests timely premium travel benefits.')
    WHEN destination_country_code = 'MEX'
      AND recent_mexico_spend_dollars > 0
      THEN 'Recent Mexico travel activity suggests this customer may value no foreign transaction fees and elevated travel rewards.'
    WHEN recent_travel_spend_dollars > 0
      THEN 'Recent travel-category spend suggests this customer may value premium travel rewards and concierge benefits.'
    ELSE 'Active card relationship and recent travel behavior suggest potential fit for premium travel benefits.'
  END AS offer_reason,
  CASE
    WHEN card_is_active
      AND credit_account_status = 'ACTIVE'
      AND destination_country_code = 'MEX'
      AND recent_mexico_spend_dollars > 0
      THEN TRUE
    ELSE FALSE
  END AS is_premium_offer_candidate
FROM candidate_rollup
