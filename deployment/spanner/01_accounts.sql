CREATE TABLE accounts (
  account_id STRING(64) NOT NULL,
  user_id STRING(64) NOT NULL,
  account_type STRING(32) NOT NULL,
  display_name STRING(128),
) PRIMARY KEY (account_id)
