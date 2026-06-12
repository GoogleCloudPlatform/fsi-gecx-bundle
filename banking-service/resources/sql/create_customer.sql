INSERT INTO `{table_ref}`
(user_id, first_name, last_name, email, phone_number, date_of_birth, tax_id_masked, kyc_status, metadata)
VALUES (@user_id, @first_name, @last_name, @email, @phone_number, NULL, NULL, 'PENDING', NULL)
