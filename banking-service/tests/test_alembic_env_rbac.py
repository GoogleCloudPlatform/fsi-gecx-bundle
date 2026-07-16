from scripts.database_lifecycle import (
    BANKING_RW_ROLE,
    CDC_RO_ROLE,
    DATA_GENERATOR_RW_ROLE,
    KYC_RW_ROLE,
    LEDGER_RW_ROLE,
    RESET_RW_ROLE,
    SCHEMA_OWNER_ROLE,
    SUPPORT_RW_ROLE,
    VIEWER_RO_ROLE,
    VOICE_RW_ROLE,
    LifecycleConfig,
    password_database_url,
    quote_identifier,
)


def test_database_role_manifest_is_explicit_and_least_privilege() -> None:
    config = LifecycleConfig(
        project_id="example-project",
        target_database="banking",
        migration_user="postgres",
        cdc_user="banking_bq_connector",
        create_missing_principals=False,
        reconcile_cdc=True,
        expected_revision="2ea57c78ba89",
        support_users=("support@example.com",),
        viewer_users=("viewer@example.com",),
    )

    assert config.memberships == {
        SCHEMA_OWNER_ROLE: ("postgres",),
        BANKING_RW_ROLE: ("banking-service-sa@example-project.iam",),
        KYC_RW_ROLE: ("kyc-service-sa@example-project.iam",),
        LEDGER_RW_ROLE: ("ledger-service-sa@example-project.iam",),
        VOICE_RW_ROLE: ("voice-agent-sa@example-project.iam",),
        DATA_GENERATOR_RW_ROLE: ("datagen-service-sa@example-project.iam",),
        RESET_RW_ROLE: ("banking-db-reset-sa@example-project.iam",),
        SUPPORT_RW_ROLE: ("support@example.com",),
        VIEWER_RO_ROLE: ("viewer@example.com",),
        CDC_RO_ROLE: ("banking_bq_connector",),
    }


def test_identifier_quoting_rejects_sql_fragments() -> None:
    assert quote_identifier("banking-service-sa@example-project.iam") == (
        '"banking-service-sa@example-project.iam"'
    )

    for unsafe in ("", "role; DROP TABLE users", 'role"name', "white space"):
        try:
            quote_identifier(unsafe)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe identifier was accepted: {unsafe!r}")


def test_cdc_password_is_added_to_a_structured_database_url() -> None:
    assert password_database_url(
        "postgresql+psycopg2://banking_bq_connector@10.0.0.1:5432/banking?sslmode=require",
        "secret-value",
    ) == (
        "postgresql+psycopg2://banking_bq_connector:secret-value@"
        "10.0.0.1:5432/banking?sslmode=require"
    )
