SELECT message_id, user_id, sender, category, message, created_at, deleted, thread_id, is_user_read, is_agent_read
FROM `{table_ref}`
WHERE user_id = @user_id AND deleted = FALSE
ORDER BY created_at ASC
