UPDATE `{table_ref}`
SET deleted = TRUE
WHERE thread_id = @thread_id AND user_id = @user_id
