UPDATE `{table_ref}`
SET first_name = @first_name,
    last_name = @last_name,
    phone_number = @phone_number
WHERE user_id = @user_id
