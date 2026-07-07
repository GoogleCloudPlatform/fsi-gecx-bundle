BEGIN
 DECLARE v_id STRING;
 DECLARE v_major INT64 DEFAULT 0;
 DECLARE v_minor INT64 DEFAULT 0;
 DECLARE v_revision INT64 DEFAULT 0;
 DECLARE v_input_version ARRAY<STRING>;
 DECLARE v_result STRING;
 DECLARE v_count INT64;
 DECLARE v_linguist_result JSON;
  SET v_id = GENERATE_UUID();
 SET p_application = LOWER(p_application);
 SET p_environment = LOWER(p_environment);
 SET v_linguist_result = PARSE_JSON(p_linguist_result);

 IF p_version IS NOT NULL AND p_version <> '0.0.0' THEN
   SET v_input_version = (
     SELECT SPLIT(p_version, ".")
   );
 END IF;

 IF ARRAY_LENGTH(v_input_version) = 3 THEN
   SET v_major = CAST(v_input_version[0] AS INT64);
   SET v_minor = CAST(v_input_version[1] AS INT64);
   SET v_revision = CAST(v_input_version[2] AS INT64);
   INSERT INTO ci.build_version(id, application, environment, event_time, repository, commit_sha, major, minor, revision, is_release, linguist_result)
   VALUES(v_id, p_application, p_environment, CURRENT_TIMESTAMP(), p_repository, p_commit_sha, v_major, v_minor, v_revision, p_is_release, v_linguist_result);
 ELSE
   SET v_count = (SELECT COUNT(id)
                   FROM ci.build_version
                   WHERE application = p_application AND environment = p_environment);

   IF v_count > 0 THEN
     SET (v_major, v_minor, v_revision) = (
       SELECT AS STRUCT major, minor, revision
       FROM ci.build_version
       WHERE application = p_application
         AND event_time = (
           SELECT MAX(event_time)
           FROM ci.build_version
           WHERE application = p_application AND environment = p_environment)
         LIMIT 1
     );
   END IF;
   SET v_revision = v_revision + 1;
   INSERT INTO ci.build_version(id, application, environment, event_time, repository, commit_sha, major, minor, revision, is_release, linguist_result)
   VALUES (v_id, p_application, p_environment, CURRENT_TIMESTAMP(), p_repository, p_commit_sha, v_major, v_minor, v_revision, p_is_release, v_linguist_result);
 END IF;
 SELECT FORMAT("BUILD_VERSION=%d.%d.%d", v_major, v_minor, v_revision);
END;
