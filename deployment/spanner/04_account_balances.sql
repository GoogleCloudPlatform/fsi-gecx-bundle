CREATE VIEW account_balances
SQL SECURITY INVOKER
AS
SELECT
  a.account_id,
  COALESCE(SUM(
    CASE
      WHEN t.direction = 'CREDIT' THEN t.amount
      WHEN t.direction = 'DEBIT' THEN -t.amount
      ELSE 0
    END
  ), 0) AS balance
FROM
  accounts a
LEFT JOIN
  transactions t ON a.account_id = t.account_id
GROUP BY
  a.account_id
