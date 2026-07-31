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

WITH LOC AS (
 SELECT
   application,
   CONCAT(major, '.', minor, '.', revision) as build_version,
   JSON_EXTRACT_SCALAR(linguist_result, '$.CSS.size') AS css_loc,
   JSON_EXTRACT_SCALAR(linguist_result, '$.Dockerfile.size') AS dockerfile_loc,
   JSON_EXTRACT_SCALAR(linguist_result, '$.HCL.size') AS hcl_loc,
   JSON_EXTRACT_SCALAR(linguist_result, '$.HTML.size') AS html_loc,
   JSON_EXTRACT_SCALAR(linguist_result, '$.Java.size') AS java_loc,
   JSON_EXTRACT_SCALAR(linguist_result, '$.JavaScript.size') AS js_loc,
   JSON_EXTRACT_SCALAR(linguist_result, '$.PLpgSQL.size') AS plpgsql_loc,
   JSON_EXTRACT_SCALAR(linguist_result, '$.Python.size') AS python_loc,
   JSON_EXTRACT_SCALAR(linguist_result, '$.Shell.size') AS shell_loc,
   JSON_EXTRACT_SCALAR(linguist_result, '$.TypeScript.size') AS typescript_loc,
 FROM ci.latest_build_version
 WHERE linguist_result IS NOT NULL
)
SELECT application, build_version, 'CSS', css_loc as loc FROM LOC
UNION ALL
SELECT application, build_version, 'Dockerfile', dockerfile_loc as loc FROM LOC
UNION ALL
SELECT application, build_version, 'HCL', hcl_loc as loc FROM LOC
UNION ALL
SELECT application, build_version, 'HTML', html_loc as loc FROM LOC
UNION ALL
SELECT application, build_version, 'Java', java_loc as loc FROM LOC
UNION ALL
SELECT application, build_version, 'Javascript', js_loc as loc FROM LOC
UNION ALL
SELECT application, build_version, 'Postgres', plpgsql_loc as loc FROM LOC
UNION ALL
SELECT application, build_version, 'Python', python_loc as loc FROM LOC
UNION ALL
SELECT application, build_version, 'Shell', shell_loc as loc FROM LOC
UNION ALL
SELECT application, build_version, 'TypeScript', typescript_loc as loc FROM LOC
