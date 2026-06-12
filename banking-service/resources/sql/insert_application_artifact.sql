INSERT INTO `{table_ref}`
(artifact_id, customer_id, application_id, claimed_artifact_type, actual_artifact_type,
 classification_confidence, status, file_path_gcs, extraction_payload, audit_metadata,
 uploaded_at, verification_tier, verification_audit, version_id)
VALUES
(@artifact_id, @customer_id, @application_id, @claimed_artifact_type, NULL,
 NULL, @status, @file_path_gcs, NULL, NULL,
 TIMESTAMP(@uploaded_at), NULL, NULL, @version_id)
