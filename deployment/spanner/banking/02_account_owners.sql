CREATE TABLE account_owners (
  account_id STRING(64) NOT NULL,
  user_id STRING(64) NOT NULL,
  owner_type STRING(32) NOT NULL,
) PRIMARY KEY (account_id, user_id),
  INTERLEAVE IN PARENT accounts ON DELETE CASCADE
