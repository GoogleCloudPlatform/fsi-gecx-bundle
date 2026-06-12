INSERT INTO `{table_ref}`
(message_id, user_id, sender, category, message, created_at, deleted, thread_id, is_user_read, is_agent_read)
VALUES (@message_id, @user_id, @sender, @category, @message, @created_at, FALSE, @thread_id, @is_user_read, @is_agent_read)
