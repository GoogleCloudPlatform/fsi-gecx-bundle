UPDATE `{table_ref}`
SET deleted = TRUE
WHERE message_id = @message_id AND user_id = @user_id
