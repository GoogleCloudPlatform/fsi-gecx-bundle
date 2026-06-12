INSERT INTO `{table_ref}`
(application_id, user_id, product_category, product_type, requested_amount, application_status, assigned_officer_id, started_at, last_updated_at)
VALUES (@application_id, @user_id, @product_category, @product_type, @requested_amount, @application_status, NULL, @started_at, @last_updated_at)
