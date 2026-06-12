UPDATE `{table_ref}`
SET
  requested_amount = COALESCE(@requested_amount, requested_amount),
  application_status = COALESCE(@application_status, application_status),
  last_updated_at = @last_updated_at
WHERE application_id = @application_id AND user_id = @user_id
