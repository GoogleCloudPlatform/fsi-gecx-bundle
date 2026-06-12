SELECT user_id
FROM `{table_ref}`
WHERE thread_id = @thread_id
LIMIT 1
