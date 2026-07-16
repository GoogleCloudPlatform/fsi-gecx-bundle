"""Deterministic PostgreSQL bootstrap, reconciliation, and verification.

Terraform owns AlloyDB users and Google Cloud IAM. Alembic owns schema
evolution. This command owns the database-level contract between those layers:
stable group roles, memberships, object ownership, grants, and Datastream CDC
prerequisites.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from typing import Iterable

import sqlalchemy as sa

from utils.database import DATABASE_URL, create_db_engine


SCHEMAS = (
    "identity",
    "kyc",
    "ledger",
    "cards",
    "operations",
    "origination",
    "audit",
    "admin",
    "catalog",
    "ref_data",
    "merchants",
    "voice_support_sessions",
)
RESET_SCHEMAS = tuple(s for s in SCHEMAS if s not in {"admin", "voice_support_sessions"})
CDC_SCHEMAS = (
    "catalog",
    "cards",
    "origination",
    "identity",
    "kyc",
    "ledger",
    "merchants",
    "operations",
)

SCHEMA_OWNER_ROLE = "banking_schema_owner"
BANKING_RW_ROLE = "banking_app_rw"
KYC_RW_ROLE = "kyc_app_rw"
LEDGER_RW_ROLE = "ledger_app_rw"
VOICE_RW_ROLE = "voice_app_rw"
DATA_GENERATOR_RW_ROLE = "data_generator_scheduler_rw"
RESET_RW_ROLE = "banking_reset_rw"
SUPPORT_RW_ROLE = "banking_support_rw"
VIEWER_RO_ROLE = "banking_viewer_ro"
CDC_RO_ROLE = "banking_cdc_ro"
DATASTREAM_REPLICATION_SLOT = "datastream_alloydb_replication_slot"

GROUP_ROLES = (
    SCHEMA_OWNER_ROLE,
    BANKING_RW_ROLE,
    KYC_RW_ROLE,
    LEDGER_RW_ROLE,
    VOICE_RW_ROLE,
    DATA_GENERATOR_RW_ROLE,
    RESET_RW_ROLE,
    SUPPORT_RW_ROLE,
    VIEWER_RO_ROLE,
    CDC_RO_ROLE,
)

RW_SCHEMA_ACCESS = {
    BANKING_RW_ROLE: (
        "identity",
        "ledger",
        "cards",
        "operations",
        "origination",
        "audit",
        "admin",
        "catalog",
        "ref_data",
        "merchants",
        "voice_support_sessions",
    ),
    KYC_RW_ROLE: ("kyc", "identity", "ref_data", "merchants"),
    LEDGER_RW_ROLE: ("ledger", "audit", "catalog", "ref_data", "merchants"),
    VOICE_RW_ROLE: ("voice_support_sessions",),
    RESET_RW_ROLE: SCHEMAS,
    SUPPORT_RW_ROLE: SCHEMAS,
}

IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_.@-]+$")


def quote_identifier(value: str) -> str:
    if not value or not IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"Unsafe PostgreSQL identifier: {value!r}")
    return f'"{value.replace(chr(34), chr(34) * 2)}"'


def comma_values(name: str) -> tuple[str, ...]:
    return tuple(value.strip() for value in os.getenv(name, "").split(",") if value.strip())


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def service_account_database_user(account_id: str, project_id: str) -> str:
    # AlloyDB IAM service-account database users use the shortened PostgreSQL
    # role form, matching the existing application connection usernames.
    return f"{account_id}@{project_id}.iam"


@dataclass(frozen=True)
class LifecycleConfig:
    project_id: str
    target_database: str
    migration_user: str
    cdc_user: str
    create_missing_principals: bool
    reconcile_cdc: bool
    expected_revision: str | None
    support_users: tuple[str, ...]
    viewer_users: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "LifecycleConfig":
        project_id = os.getenv("PROJECT_ID", "").strip()
        if not project_id:
            raise RuntimeError("PROJECT_ID is required for database lifecycle operations.")
        return cls(
            project_id=project_id,
            target_database=os.getenv("DB_TARGET_DATABASE", "banking").strip(),
            migration_user=os.getenv("DB_MIGRATION_DATABASE_USER", "postgres").strip(),
            cdc_user=os.getenv("CDC_REPLICATION_USER", "banking_bq_connector").strip(),
            create_missing_principals=env_flag("DB_BOOTSTRAP_CREATE_PRINCIPALS"),
            reconcile_cdc=env_flag("DB_RECONCILE_CDC", default=True),
            expected_revision=os.getenv("EXPECTED_ALEMBIC_REVISION") or None,
            support_users=comma_values("IAM_DBA_USERS"),
            viewer_users=comma_values("IAM_DB_VIEWER_USERS"),
        )

    @property
    def memberships(self) -> dict[str, tuple[str, ...]]:
        return {
            SCHEMA_OWNER_ROLE: (self.migration_user,),
            BANKING_RW_ROLE: (
                service_account_database_user("banking-service-sa", self.project_id),
            ),
            KYC_RW_ROLE: (
                service_account_database_user("kyc-service-sa", self.project_id),
            ),
            LEDGER_RW_ROLE: (
                service_account_database_user("ledger-service-sa", self.project_id),
            ),
            VOICE_RW_ROLE: (
                service_account_database_user("voice-agent-sa", self.project_id),
            ),
            DATA_GENERATOR_RW_ROLE: (
                service_account_database_user("datagen-service-sa", self.project_id),
            ),
            RESET_RW_ROLE: (
                service_account_database_user("banking-db-reset-sa", self.project_id),
            ),
            SUPPORT_RW_ROLE: self.support_users,
            VIEWER_RO_ROLE: self.viewer_users,
            CDC_RO_ROLE: (self.cdc_user,),
        }

    @property
    def principals(self) -> tuple[str, ...]:
        return tuple(
            sorted({member for members in self.memberships.values() for member in members})
        )


def role_exists(connection: sa.Connection, role: str) -> bool:
    return bool(
        connection.execute(
            sa.text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": role}
        ).scalar()
    )


def create_group_roles(connection: sa.Connection) -> None:
    for role in GROUP_ROLES:
        if not role_exists(connection, role):
            connection.execute(sa.text(f"CREATE ROLE {quote_identifier(role)} NOLOGIN"))


def ensure_principals(connection: sa.Connection, config: LifecycleConfig) -> None:
    missing = [role for role in config.principals if not role_exists(connection, role)]
    if missing and not config.create_missing_principals:
        raise RuntimeError(
            "Terraform-managed database principals are missing: " + ", ".join(missing)
        )
    for role in missing:
        connection.execute(sa.text(f"CREATE ROLE {quote_identifier(role)} LOGIN"))


def grant_memberships(connection: sa.Connection, config: LifecycleConfig) -> None:
    for group, members in config.memberships.items():
        for member in members:
            connection.execute(
                sa.text(
                    f"GRANT {quote_identifier(group)} TO {quote_identifier(member)}"
                )
            )


def bootstrap(connection: sa.Connection, config: LifecycleConfig) -> dict[str, object]:
    create_group_roles(connection)
    ensure_principals(connection, config)
    grant_memberships(connection, config)
    qdatabase = quote_identifier(config.target_database)
    qowner = quote_identifier(SCHEMA_OWNER_ROLE)
    connection.execute(
        sa.text(
            f"GRANT CONNECT, CREATE, TEMPORARY ON DATABASE {qdatabase} TO {qowner}"
        )
    )
    return {
        "phase": "bootstrap",
        "group_roles": list(GROUP_ROLES),
        "principals": list(config.principals),
        "status": "ok",
    }


def ensure_database(engine: sa.Engine, config: LifecycleConfig) -> None:
    """Create the application database before Alembic runs, idempotently."""
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        exists = connection.execute(
            sa.text("SELECT 1 FROM pg_database WHERE datname = :database"),
            {"database": config.target_database},
        ).scalar()
        if not exists:
            connection.execute(
                sa.text(f"CREATE DATABASE {quote_identifier(config.target_database)}")
            )


def grant_database_connect(connection: sa.Connection, roles: Iterable[str]) -> None:
    database = connection.execute(sa.text("SELECT current_database()")) .scalar_one()
    for role in roles:
        connection.execute(
            sa.text(
                f"GRANT CONNECT ON DATABASE {quote_identifier(database)} "
                f"TO {quote_identifier(role)}"
            )
        )


def reconcile_ownership(connection: sa.Connection) -> None:
    for schema in SCHEMAS:
        connection.execute(
            sa.text(
                f"ALTER SCHEMA {quote_identifier(schema)} OWNER TO "
                f"{quote_identifier(SCHEMA_OWNER_ROLE)}"
            )
        )

    objects = connection.execute(
        sa.text(
            """
            SELECT n.nspname, c.relname, c.relkind
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = ANY(:schemas)
              AND c.relkind IN ('r', 'p', 'v', 'm', 'S')
            ORDER BY n.nspname, c.relname
            """
        ),
        {"schemas": list(SCHEMAS)},
    ).all()
    for schema, name, kind in objects:
        object_type = "SEQUENCE" if kind == "S" else "MATERIALIZED VIEW" if kind == "m" else "VIEW" if kind == "v" else "TABLE"
        connection.execute(
            sa.text(
                f"ALTER {object_type} {quote_identifier(schema)}.{quote_identifier(name)} "
                f"OWNER TO {quote_identifier(SCHEMA_OWNER_ROLE)}"
            )
        )


def grant_rw_schema(connection: sa.Connection, role: str, schema: str) -> None:
    qrole = quote_identifier(role)
    qschema = quote_identifier(schema)
    connection.execute(sa.text(f"GRANT USAGE ON SCHEMA {qschema} TO {qrole}"))
    connection.execute(
        sa.text(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {qschema} TO {qrole}"
        )
    )
    connection.execute(
        sa.text(
            f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA {qschema} TO {qrole}"
        )
    )
    connection.execute(
        sa.text(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {quote_identifier(SCHEMA_OWNER_ROLE)} "
            f"IN SCHEMA {qschema} GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {qrole}"
        )
    )
    connection.execute(
        sa.text(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {quote_identifier(SCHEMA_OWNER_ROLE)} "
            f"IN SCHEMA {qschema} GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {qrole}"
        )
    )


def reconcile_grants(connection: sa.Connection) -> None:
    grant_database_connect(connection, GROUP_ROLES)
    for role, schemas in RW_SCHEMA_ACCESS.items():
        for schema in schemas:
            grant_rw_schema(connection, role, schema)

    qreset = quote_identifier(RESET_RW_ROLE)
    qowner = quote_identifier(SCHEMA_OWNER_ROLE)
    for schema in SCHEMAS:
        qschema = quote_identifier(schema)
        connection.execute(
            sa.text(f"GRANT TRUNCATE ON ALL TABLES IN SCHEMA {qschema} TO {qreset}")
        )
        connection.execute(
            sa.text(
                f"ALTER DEFAULT PRIVILEGES FOR ROLE {qowner} IN SCHEMA {qschema} "
                f"GRANT TRUNCATE ON TABLES TO {qreset}"
            )
        )

    qdata_generator = quote_identifier(DATA_GENERATOR_RW_ROLE)
    connection.execute(
        sa.text(f"GRANT USAGE ON SCHEMA operations TO {qdata_generator}")
    )
    connection.execute(
        sa.text(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "
            f"operations.synthetic_scheduled_events TO {qdata_generator}"
        )
    )
    connection.execute(
        sa.text(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {qowner} IN SCHEMA operations "
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {qdata_generator}"
        )
    )

    qviewer = quote_identifier(VIEWER_RO_ROLE)
    for schema in RESET_SCHEMAS:
        qschema = quote_identifier(schema)
        connection.execute(sa.text(f"GRANT USAGE ON SCHEMA {qschema} TO {qviewer}"))
        connection.execute(
            sa.text(f"GRANT SELECT ON ALL TABLES IN SCHEMA {qschema} TO {qviewer}")
        )
        connection.execute(
            sa.text(
                f"ALTER DEFAULT PRIVILEGES FOR ROLE {qowner} IN SCHEMA {qschema} "
                f"GRANT SELECT ON TABLES TO {qviewer}"
            )
        )

    qcdc = quote_identifier(CDC_RO_ROLE)
    for schema in CDC_SCHEMAS:
        qschema = quote_identifier(schema)
        connection.execute(sa.text(f"GRANT USAGE ON SCHEMA {qschema} TO {qcdc}"))
        connection.execute(
            sa.text(f"GRANT SELECT ON ALL TABLES IN SCHEMA {qschema} TO {qcdc}")
        )
        connection.execute(
            sa.text(
                f"ALTER DEFAULT PRIVILEGES FOR ROLE {qowner} IN SCHEMA {qschema} "
                f"GRANT SELECT ON TABLES TO {qcdc}"
            )
        )

    connection.execute(
        sa.text(
            f"GRANT CREATE ON SCHEMA voice_support_sessions TO {quote_identifier(VOICE_RW_ROLE)}"
        )
    )

    for role in (
        BANKING_RW_ROLE,
        KYC_RW_ROLE,
        LEDGER_RW_ROLE,
        VOICE_RW_ROLE,
        DATA_GENERATOR_RW_ROLE,
        SUPPORT_RW_ROLE,
        VIEWER_RO_ROLE,
        CDC_RO_ROLE,
    ):
        connection.execute(
            sa.text(
                "REVOKE UPDATE, DELETE ON TABLE ledger.account_ledger FROM "
                f"{quote_identifier(role)}"
            )
        )
    connection.execute(
        sa.text("REVOKE UPDATE, DELETE ON TABLE ledger.account_ledger FROM PUBLIC")
    )


def reconcile_cdc(connection: sa.Connection, config: LifecycleConfig) -> None:
    connection.execute(
        sa.text(f"ALTER ROLE {quote_identifier(config.cdc_user)} WITH REPLICATION")
    )
    publication_exists = connection.execute(
        sa.text("SELECT 1 FROM pg_publication WHERE pubname = 'datastream_publication'")
    ).scalar()
    if not publication_exists:
        connection.execute(
            sa.text("CREATE PUBLICATION datastream_publication FOR ALL TABLES")
        )


def ensure_replication_slot(engine: sa.Engine, config: LifecycleConfig) -> None:
    if not config.reconcile_cdc:
        return
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        wal_level = connection.execute(sa.text("SHOW wal_level")).scalar_one()
        if wal_level != "logical":
            raise RuntimeError(
                f"PostgreSQL wal_level is {wal_level!r}; AlloyDB logical decoding must be enabled."
            )
        slot_exists = connection.execute(
            sa.text(
                "SELECT 1 FROM pg_replication_slots "
                f"WHERE slot_name = '{DATASTREAM_REPLICATION_SLOT}'"
            )
        ).scalar()
        if not slot_exists:
            connection.execute(
                sa.text(
                    "SELECT pg_create_logical_replication_slot(" 
                    f"'{DATASTREAM_REPLICATION_SLOT}', 'pgoutput')"
                )
            )


def reconcile(
    engine: sa.Engine,
    config: LifecycleConfig,
    *,
    replication_engine: sa.Engine | None = None,
) -> dict[str, object]:
    with engine.begin() as connection:
        reconcile_ownership(connection)
        reconcile_grants(connection)
        if config.reconcile_cdc:
            reconcile_cdc(connection, config)
    ensure_replication_slot(replication_engine or engine, config)
    return verify(engine, config, phase="reconcile")


def password_database_url(url: str, password: str) -> str:
    """Add a secret-sourced password without interpolating it in Terraform."""
    if not url or not password:
        raise RuntimeError(
            "CDC_DATABASE_URL and CDC_DB_PASSWORD are required for CDC reconciliation."
        )
    return sa.engine.make_url(url).set(password=password).render_as_string(
        hide_password=False
    )


def membership_exists(connection: sa.Connection, group: str, member: str) -> bool:
    return bool(
        connection.execute(
            sa.text(
                """
                SELECT 1
                FROM pg_auth_members m
                JOIN pg_roles parent ON parent.oid = m.roleid
                JOIN pg_roles child ON child.oid = m.member
                WHERE parent.rolname = :group AND child.rolname = :member
                """
            ),
            {"group": group, "member": member},
        ).scalar()
    )


def verify(
    engine: sa.Engine, config: LifecycleConfig, *, phase: str = "verify"
) -> dict[str, object]:
    errors: list[str] = []
    with engine.connect() as connection:
        for role in (*GROUP_ROLES, *config.principals):
            if not role_exists(connection, role):
                errors.append(f"missing role: {role}")

        for group, members in config.memberships.items():
            for member in members:
                if role_exists(connection, group) and role_exists(connection, member):
                    if not membership_exists(connection, group, member):
                        errors.append(f"missing membership: {member} -> {group}")

        wrong_schema_owners = connection.execute(
            sa.text(
                """
                SELECT nspname, pg_get_userbyid(nspowner)
                FROM pg_namespace
                WHERE nspname = ANY(:schemas)
                  AND pg_get_userbyid(nspowner) <> :owner
                ORDER BY nspname
                """
            ),
            {"schemas": list(SCHEMAS), "owner": SCHEMA_OWNER_ROLE},
        ).all()
        errors.extend(
            f"wrong schema owner: {schema} owned by {owner}"
            for schema, owner in wrong_schema_owners
        )

        wrong_object_owners = connection.execute(
            sa.text(
                """
                SELECT n.nspname, c.relname, pg_get_userbyid(c.relowner)
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = ANY(:schemas)
                  AND c.relkind IN ('r', 'p', 'v', 'm', 'S')
                  AND pg_get_userbyid(c.relowner) <> :owner
                ORDER BY n.nspname, c.relname
                """
            ),
            {"schemas": list(SCHEMAS), "owner": SCHEMA_OWNER_ROLE},
        ).all()
        errors.extend(
            f"wrong object owner: {schema}.{name} owned by {owner}"
            for schema, name, owner in wrong_object_owners
        )

        revision = connection.execute(
            sa.text("SELECT version_num FROM admin.alembic_version")
        ).scalar()
        if not revision:
            errors.append("admin.alembic_version is empty")
        if config.expected_revision and revision != config.expected_revision:
            errors.append(
                f"Alembic revision is {revision!r}, expected {config.expected_revision!r}"
            )

        global_epoch = connection.execute(
            sa.text(
                "SELECT epoch FROM voice_support_sessions.reset_epochs "
                "WHERE scope_type = 'GLOBAL' AND scope_id = '*'"
            )
        ).scalar()
        if global_epoch is None:
            errors.append("voice-support GLOBAL reset epoch is missing")

        for role in (BANKING_RW_ROLE, SUPPORT_RW_ROLE, VIEWER_RO_ROLE, CDC_RO_ROLE):
            can_update, can_delete = connection.execute(
                sa.text(
                    "SELECT "
                    "has_table_privilege(:role, 'ledger.account_ledger', 'UPDATE'), "
                    "has_table_privilege(:role, 'ledger.account_ledger', 'DELETE')"
                ),
                {"role": role},
            ).one()
            if can_update or can_delete:
                errors.append(f"immutable ledger permissions are too broad for {role}")

        if config.reconcile_cdc and role_exists(connection, config.cdc_user):
            cdc_replication = connection.execute(
                sa.text("SELECT rolreplication FROM pg_roles WHERE rolname = :role"),
                {"role": config.cdc_user},
            ).scalar()
            if not cdc_replication:
                errors.append(f"CDC role lacks REPLICATION: {config.cdc_user}")
            publication = connection.execute(
                sa.text("SELECT 1 FROM pg_publication WHERE pubname = 'datastream_publication'")
            ).scalar()
            if not publication:
                errors.append("Datastream publication is missing")
            slot = connection.execute(
                sa.text(
                    "SELECT 1 FROM pg_replication_slots "
                    f"WHERE slot_name = '{DATASTREAM_REPLICATION_SLOT}'"
                )
            ).scalar()
            if not slot:
                errors.append("Datastream replication slot is missing")

    result = {
        "phase": phase,
        "status": "error" if errors else "ok",
        "alembic_revision": revision,
        "errors": errors,
    }
    if errors:
        raise RuntimeError(json.dumps(result, sort_keys=True))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("bootstrap", "reconcile", "verify"))
    args = parser.parse_args()

    config = LifecycleConfig.from_env()
    engine = create_db_engine(DATABASE_URL)
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Database lifecycle commands require PostgreSQL.")

    if args.command == "bootstrap":
        ensure_database(engine, config)
        with engine.begin() as connection:
            result = bootstrap(connection, config)
    elif args.command == "reconcile":
        replication_engine = None
        if config.reconcile_cdc:
            replication_engine = sa.create_engine(
                password_database_url(
                    os.getenv("CDC_DATABASE_URL", ""),
                    os.getenv("CDC_DB_PASSWORD", ""),
                ),
                pool_pre_ping=True,
            )
        result = reconcile(engine, config, replication_engine=replication_engine)
    else:
        result = verify(engine, config)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
