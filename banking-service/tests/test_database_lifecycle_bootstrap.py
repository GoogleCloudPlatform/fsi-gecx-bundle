from unittest.mock import MagicMock, patch

from scripts.database_lifecycle import (
    BANKING_RW_ROLE,
    RW_SCHEMA_ACCESS,
    LifecycleConfig,
    bootstrap,
    reconcile_ownership,
    reconcile_grants,
)


def lifecycle_config() -> LifecycleConfig:
    return LifecycleConfig(
        project_id="example-project",
        target_database="banking",
        migration_user="migration@example-project.iam",
        cdc_user="banking_bq_connector",
        create_missing_principals=False,
        reconcile_cdc=True,
        expected_revision=None,
        support_users=(),
        viewer_users=(),
    )


def test_bootstrap_delegates_schema_creation_to_schema_owner() -> None:
    connection = MagicMock()
    config = lifecycle_config()

    with (
        patch("scripts.database_lifecycle.create_group_roles"),
        patch("scripts.database_lifecycle.ensure_principals"),
        patch("scripts.database_lifecycle.grant_memberships"),
    ):
        bootstrap(connection, config)

    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert (
        'GRANT CONNECT, CREATE, TEMPORARY ON DATABASE "banking" '
        'TO "banking_schema_owner"'
    ) in statements


def test_reconcile_grants_reset_role_truncate_without_broadening_app_roles() -> None:
    connection = MagicMock()

    with patch("scripts.database_lifecycle.grant_database_connect"):
        reconcile_grants(connection)

    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert (
        'GRANT TRUNCATE ON ALL TABLES IN SCHEMA "operations" TO "banking_reset_rw"'
    ) in statements
    assert (
        'ALTER DEFAULT PRIVILEGES FOR ROLE "banking_schema_owner" '
        'IN SCHEMA "operations" GRANT TRUNCATE ON TABLES TO "banking_reset_rw"'
    ) in statements
    assert not any(
        "GRANT TRUNCATE" in statement and 'TO "banking_app_rw"' in statement
        for statement in statements
    )


def test_reconcile_ownership_temporarily_assumes_known_runtime_owner() -> None:
    connection = MagicMock()
    current_user_result = MagicMock()
    current_user_result.scalar_one.return_value = "migration@example-project.iam"
    owners_result = MagicMock()
    owners_result.scalars.return_value = ["voice-agent-sa@example-project.iam"]
    membership_result = MagicMock()
    membership_result.scalar.return_value = None
    objects_result = MagicMock()
    objects_result.all.return_value = [
        ("voice_support_sessions", "adk_internal_metadata", "r")
    ]

    def execute(statement, *args, **kwargs):
        sql = str(statement)
        if sql == "SELECT current_user":
            return current_user_result
        if "SELECT DISTINCT owner" in sql:
            return owners_result
        if "FROM pg_auth_members" in sql:
            return membership_result
        if "SELECT n.nspname, c.relname, c.relkind" in sql:
            return objects_result
        return MagicMock()

    connection.execute.side_effect = execute
    reconcile_ownership(connection, lifecycle_config())

    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    runtime_owner = '"voice-agent-sa@example-project.iam"'
    migration_user = '"migration@example-project.iam"'
    assert f"GRANT {runtime_owner} TO {migration_user}" in statements
    assert (
        'ALTER TABLE "voice_support_sessions"."adk_internal_metadata" '
        'OWNER TO "banking_schema_owner"'
    ) in statements
    assert f"REVOKE {runtime_owner} FROM {migration_user}" in statements


def test_banking_runtime_can_atomically_provision_kyc_records() -> None:
    assert "kyc" in RW_SCHEMA_ACCESS[BANKING_RW_ROLE]

    connection = MagicMock()
    with patch("scripts.database_lifecycle.grant_database_connect"):
        reconcile_grants(connection)

    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert 'GRANT USAGE ON SCHEMA "kyc" TO "banking_app_rw"' in statements
    assert (
        'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "kyc" '
        'TO "banking_app_rw"'
    ) in statements
