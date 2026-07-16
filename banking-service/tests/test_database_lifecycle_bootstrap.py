from unittest.mock import MagicMock, patch

from scripts.database_lifecycle import LifecycleConfig, bootstrap


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
