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

WITH TOTAL_BUILDS AS (
 SELECT
   application,
   environment,
   COUNT(id) AS build_count
 FROM ci.build_version
 GROUP BY application, environment
)
SELECT
 B1.*,
 T.build_count
FROM ci.build_version AS B1
INNER JOIN TOTAL_BUILDS AS T ON B1.application = T.application AND B1.environment = T.environment
WHERE B1.event_time = (
 SELECT MAX(B2.event_time)
 FROM ci.build_version AS B2
 WHERE B1.application = B2.application AND B1.environment = B2.environment
)
