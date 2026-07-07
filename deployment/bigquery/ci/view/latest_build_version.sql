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
