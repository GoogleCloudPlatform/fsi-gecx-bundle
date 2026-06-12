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

UPDATE `{table_ref}`
SET status = @status,
    actual_artifact_type = @actual_type,
    classification_confidence = @confidence,
    extraction_payload = TO_JSON(PARSE_JSON(@payload)),
    audit_metadata = TO_JSON(PARSE_JSON(@audit)),
    verification_tier = @verification_tier,
    version_id = @version_id
WHERE artifact_id = @artifact_id
