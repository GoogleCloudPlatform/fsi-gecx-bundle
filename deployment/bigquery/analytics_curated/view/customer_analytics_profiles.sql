CREATE OR REPLACE VIEW `__PROJECT_ID__.analytics_curated.customer_analytics_profiles` AS
WITH primary_address AS (
  SELECT
    user_id,
    city,
    state,
    postal_code,
    country_code,
    verified_by_doc_ai
  FROM `__PROJECT_ID__.iceberg_catalog.identity_user_addresses`
  WHERE is_primary IS TRUE
  QUALIFY ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at DESC, id DESC) = 1
),
latest_credit_profile AS (
  SELECT
    user_id,
    credit_score,
    credit_tier,
    stated_annual_income_cents
  FROM `__PROJECT_ID__.iceberg_catalog.kyc_user_credit_profiles`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at DESC, id DESC) = 1
),
credit_account_summary AS (
  SELECT
    customer_id,
    COUNT(*) AS credit_account_count,
    COUNTIF(UPPER(status) = 'ACTIVE') AS active_credit_account_count,
    SUM(credit_limit_cents) AS total_credit_limit_cents,
    SUM(cleared_balance_cents) AS total_cleared_balance_cents,
    SUM(available_credit_cents) AS total_available_credit_cents
  FROM `__PROJECT_ID__.iceberg_catalog.cards_credit_accounts`
  GROUP BY customer_id
)
SELECT
  user.id AS customer_id,
  CONCAT(user.first_name, ' ', user.last_name) AS customer_name,
  user.created_at AS customer_since,
  address.city AS home_city,
  address.state AS home_state,
  address.postal_code AS home_postal_code,
  UPPER(address.country_code) AS home_country_code,
  CASE
    WHEN UPPER(address.country_code) IN ('US', 'USA')
      AND UPPER(address.state) = 'CA'
      AND UPPER(address.city) IN (
        'SAN FRANCISCO', 'MOUNTAIN VIEW', 'PALO ALTO', 'LOS ALTOS',
        'LOS ALTOS HILLS', 'MENLO PARK', 'WOODSIDE', 'ATHERTON',
        'PORTOLA VALLEY', 'HILLSBOROUGH', 'SARATOGA', 'SAN JOSE',
        'OAKLAND', 'BERKELEY', 'FREMONT', 'SANTA CLARA', 'SUNNYVALE'
      )
      THEN 'San Francisco Bay Area'
    WHEN UPPER(address.country_code) IN ('US', 'USA')
      AND UPPER(address.state) = 'CA' AND UPPER(address.city) = 'LOS ANGELES'
      THEN 'Los Angeles'
    WHEN UPPER(address.country_code) IN ('US', 'USA')
      AND UPPER(address.state) = 'TX' AND UPPER(address.city) = 'DALLAS'
      THEN 'Dallas–Fort Worth'
    WHEN UPPER(address.country_code) IN ('US', 'USA')
      AND UPPER(address.state) = 'TX' AND UPPER(address.city) = 'HOUSTON'
      THEN 'Houston'
    WHEN UPPER(address.country_code) IN ('US', 'USA')
      AND UPPER(address.state) = 'IL' AND UPPER(address.city) = 'CHICAGO'
      THEN 'Chicago'
    WHEN UPPER(address.country_code) IN ('US', 'USA')
      AND UPPER(address.state) = 'NY' AND UPPER(address.city) = 'NEW YORK'
      THEN 'New York City'
    WHEN UPPER(address.country_code) IN ('US', 'USA')
      AND UPPER(address.state) = 'WA' AND UPPER(address.city) = 'SEATTLE'
      THEN 'Seattle'
    WHEN UPPER(address.country_code) IN ('US', 'USA')
      AND UPPER(address.state) = 'FL' AND UPPER(address.city) = 'MIAMI'
      THEN 'Miami'
    WHEN UPPER(address.country_code) IN ('US', 'USA')
      AND UPPER(address.state) = 'GA' AND UPPER(address.city) = 'ATLANTA'
      THEN 'Atlanta'
    WHEN UPPER(address.country_code) IN ('US', 'USA')
      THEN CONCAT(INITCAP(address.city), ', ', UPPER(address.state))
  END AS metropolitan_area,
  CASE
    WHEN UPPER(address.state) = 'CA'
      AND UPPER(address.city) IN (
        'SAN FRANCISCO', 'MOUNTAIN VIEW', 'PALO ALTO', 'LOS ALTOS',
        'LOS ALTOS HILLS', 'MENLO PARK', 'WOODSIDE', 'ATHERTON',
        'PORTOLA VALLEY', 'HILLSBOROUGH', 'SARATOGA', 'SAN JOSE',
        'OAKLAND', 'BERKELEY', 'FREMONT', 'SANTA CLARA', 'SUNNYVALE',
        'SACRAMENTO'
      )
      THEN 'Northern California'
    WHEN UPPER(address.state) = 'CA'
      THEN 'Southern California'
    ELSE UPPER(address.state)
  END AS home_region,
  address.verified_by_doc_ai AS address_verified_by_doc_ai,
  credit.credit_score,
  credit.credit_tier,
  credit.stated_annual_income_cents / 100.0 AS stated_annual_income_dollars,
  COALESCE(accounts.credit_account_count, 0) AS credit_account_count,
  COALESCE(accounts.active_credit_account_count, 0) AS active_credit_account_count,
  COALESCE(accounts.total_credit_limit_cents, 0) / 100.0 AS total_credit_limit_dollars,
  COALESCE(accounts.total_cleared_balance_cents, 0) / 100.0 AS total_cleared_balance_dollars,
  COALESCE(accounts.total_available_credit_cents, 0) / 100.0 AS total_available_credit_dollars
FROM `__PROJECT_ID__.iceberg_catalog.identity_users` user
LEFT JOIN primary_address address
  ON user.id = address.user_id
LEFT JOIN latest_credit_profile credit
  ON user.id = credit.user_id
LEFT JOIN credit_account_summary accounts
  ON user.id = accounts.customer_id
