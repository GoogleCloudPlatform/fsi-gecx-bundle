MERGE `{table_ref}` T
USING (SELECT @user_id AS user_id, @device_token AS device_token) S
ON T.user_id = S.user_id AND T.device_token = S.device_token
WHEN NOT MATCHED THEN
  INSERT (user_id, device_token) VALUES (user_id, device_token)
