-- Copyright 2026 Google LLC
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--     https://www.apache.org/licenses/LICENSE-2.0
--
-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.

SELECT 
    a.artifact_id, 
    a.customer_id, 
    a.application_id, 
    a.claimed_artifact_type, 
    a.actual_artifact_type, 
    a.status, 
    a.file_path_gcs, 
    a.extraction_payload, 
    a.audit_metadata, 
    a.verification_tier, 
    a.version_id,
    u.first_name AS user_first_name,
    u.last_name AS user_last_name,
    u.email AS user_email,
    app.requested_amount,
    app.product_category,
    app.product_type
FROM `{table_ref}` a
LEFT JOIN `{user_table_ref}` u ON a.customer_id = u.user_id
LEFT JOIN `{application_table_ref}` app ON a.application_id = app.application_id
WHERE a.status IN ('MISMATCH', 'PENDING_REVIEW')
ORDER BY a.uploaded_at DESC
