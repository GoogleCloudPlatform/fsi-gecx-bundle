from unittest.mock import MagicMock, patch

from scripts.database_lifecycle import LifecycleConfig, bootstrap, reconcile_grants


def test_bootstrap_delegates_schema_creation_to_schema_owner() -> None:
    connection = MagicMock()
    config = LifecycleConfig(
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
        'GRANT TRUNCATE ON ALL TABLES IN SCHEMA "operations" '
        'TO "banking_reset_rw"'
    ) in statements
    assert (
        'ALTER DEFAULT PRIVILEGES FOR ROLE "banking_schema_owner" '
        'IN SCHEMA "operations" GRANT TRUNCATE ON TABLES TO "banking_reset_rw"'
    ) in statements
    assert not any(
        "GRANT TRUNCATE" in statement and 'TO "banking_app_rw"' in statement
        for statement in statements
    )
