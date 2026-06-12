SELECT user_id, first_name, last_name, email, phone_number 
FROM `{table_ref}`
WHERE user_id = @user_id
LIMIT 1
