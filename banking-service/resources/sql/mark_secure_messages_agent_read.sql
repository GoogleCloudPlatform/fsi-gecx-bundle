UPDATE `{table_ref}`
SET is_agent_read = TRUE
WHERE user_id = @user_id AND message_id IN UNNEST(@message_ids)
