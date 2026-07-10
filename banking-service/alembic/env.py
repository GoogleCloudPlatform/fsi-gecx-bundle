import os
import sys
import logging
from logging.config import fileConfig

import sqlalchemy as sa
from sqlalchemy import pool
from sqlalchemy.engine.url import make_url

from alembic import context

os.environ.setdefault("ALEMBIC_RUNNING", "true")

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Append the parent banking-service directory to sys.path so python resolves local package imports correctly
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))

from utils.database import Base, DATABASE_URL  # noqa: E402
# Import all database models to ensure they register on Base.metadata for autogenerate detection
import models.credit_card  # noqa: E402, F401
import models.support  # noqa: E402, F401
import models.settings  # noqa: E402, F401
import models.identity  # noqa: E402, F401
import models.origination  # noqa: E402, F401
import models.audit  # noqa: E402, F401
import models.kyc  # noqa: E402, F401
import models.reference  # noqa: E402, F401
import models.merchant  # noqa: E402, F401
import models.fraud  # noqa: E402, F401

# Set target metadata for alembic schema scanning
target_metadata = Base.metadata

# Inject the dynamic DATABASE_URL connection string directly into the alembic configuration
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Configure masked database URL for logging safety
logger = logging.getLogger("alembic.runtime.environment")
try:
    parsed_url = make_url(DATABASE_URL)
    masked_url = parsed_url._replace(password="********").render_as_string(hide_password=False)
except Exception:
    masked_url = "Redacted Connection String"

IS_SQLITE_URL = str(DATABASE_URL).startswith("sqlite")
SQLITE_AUTOGEN_IGNORED_SCHEMAS = {"merchants", "ref_data"}

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def compare_type(context, inspected_column, metadata_column, inspected_type, metadata_type):
    if context.dialect.name == "sqlite":
        return False
    return None


def _autogenerate_requested() -> bool:
    return bool(getattr(config.cmd_opts, "autogenerate", False))


def _object_schema(obj, compare_to):
    for candidate in (obj, compare_to):
        if candidate is None:
            continue
        schema = getattr(candidate, "schema", None)
        if schema:
            return schema
        table = getattr(candidate, "table", None)
        if table is not None and getattr(table, "schema", None):
            return table.schema
    return None


def include_object(obj, name, type_, reflected, compare_to):
    if not _autogenerate_requested():
        return True

    if IS_SQLITE_URL and type_ == "foreign_key_constraint":
        return False

    if IS_SQLITE_URL and _object_schema(obj, compare_to) in SQLITE_AUTOGEN_IGNORED_SCHEMAS:
        return False

    return True


def process_revision_directives(context, revision, directives):
    if _autogenerate_requested() and directives:
        script = directives[0]
        if script.upgrade_ops.is_empty():
            directives[:] = []
            logger.info("Autogenerate detected no schema changes.")
            return

    if context.dialect.name == "sqlite":
        script = directives[0]
        if hasattr(script, "upgrade_ops") and hasattr(script.upgrade_ops, "ops"):
            new_ops = []
            for op in script.upgrade_ops.ops:
                if op.__class__.__name__ == "ModifyTableOps":
                    op.ops = [sub for sub in op.ops if sub.__class__.__name__ != "CreateForeignKeyOp"]
                    if op.ops:
                        new_ops.append(op)
                elif op.__class__.__name__ != "CreateForeignKeyOp":
                    new_ops.append(op)
            script.upgrade_ops.ops = new_ops
        if hasattr(script, "downgrade_ops") and hasattr(script.downgrade_ops, "ops"):
            new_ops = []
            for op in script.downgrade_ops.ops:
                if op.__class__.__name__ == "ModifyTableOps":
                    op.ops = [sub for sub in op.ops if sub.__class__.__name__ != "DropConstraintOp"]
                    if op.ops:
                        new_ops.append(op)
                elif op.__class__.__name__ != "DropConstraintOp":
                    new_ops.append(op)
            script.downgrade_ops.ops = new_ops


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    logger.info(f"Running offline migrations against: {masked_url}")
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        include_object=include_object,
        compare_foreign_keys=False,
        process_revision_directives=process_revision_directives,
        version_table_schema="admin" if (url and url.startswith("postgresql")) else None,
    )

    with context.begin_transaction():
        if url and url.startswith("postgresql"):
            context.execute("CREATE SCHEMA IF NOT EXISTS identity;")
            context.execute("CREATE SCHEMA IF NOT EXISTS kyc;")
            context.execute("CREATE SCHEMA IF NOT EXISTS ledger;")
            context.execute("CREATE SCHEMA IF NOT EXISTS cards;")
            context.execute("CREATE SCHEMA IF NOT EXISTS operations;")
            context.execute("CREATE SCHEMA IF NOT EXISTS origination;")
            context.execute("CREATE SCHEMA IF NOT EXISTS audit;")
            context.execute("CREATE SCHEMA IF NOT EXISTS admin;")
            context.execute("CREATE SCHEMA IF NOT EXISTS catalog;")
            context.execute("CREATE SCHEMA IF NOT EXISTS ref_data;")
            context.execute("CREATE SCHEMA IF NOT EXISTS merchants;")
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    logger.info(f"Running online migrations against: {masked_url}")
    from utils.database import create_db_engine
    connectable = create_db_engine(DATABASE_URL, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        # Detect if we are deploying against PostgreSQL to prevent horizontal scaling lock contention
        is_postgres = connection.dialect.name == "postgresql"

        if is_postgres:
            connection.execute(sa.text("CREATE SCHEMA IF NOT EXISTS identity;"))
            connection.execute(sa.text("CREATE SCHEMA IF NOT EXISTS kyc;"))
            connection.execute(sa.text("CREATE SCHEMA IF NOT EXISTS ledger;"))
            connection.execute(sa.text("CREATE SCHEMA IF NOT EXISTS cards;"))
            connection.execute(sa.text("CREATE SCHEMA IF NOT EXISTS operations;"))
            connection.execute(sa.text("CREATE SCHEMA IF NOT EXISTS origination;"))
            connection.execute(sa.text("CREATE SCHEMA IF NOT EXISTS audit;"))
            connection.execute(sa.text("CREATE SCHEMA IF NOT EXISTS admin;"))
            connection.execute(sa.text("CREATE SCHEMA IF NOT EXISTS catalog;"))
            connection.execute(sa.text("CREATE SCHEMA IF NOT EXISTS ref_data;"))
            connection.execute(sa.text("CREATE SCHEMA IF NOT EXISTS merchants;"))
            connection.execute(sa.text("ALTER TABLE IF EXISTS public.alembic_version SET SCHEMA admin;"))
            connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_object=include_object,
            compare_foreign_keys=False,
            process_revision_directives=process_revision_directives,
            version_table_schema="admin" if is_postgres else None,
        )

        with context.begin_transaction():
            if is_postgres:
                logger.info("Acquiring transactional advisory migration lock (ID: 592837410)...")
                connection.execute(sa.text("SELECT pg_advisory_xact_lock(592837410);"))
            context.run_migrations()

            if is_postgres and os.getenv("SKIP_IAM_GRANTS") != "true":
                logger.info("Applying programmatic post-migration RBAC permission grants across all schemas...")
                try:
                    from utils.gcp import get_project_id
                    project_id = get_project_id()
                    if str(project_id) == "None":
                        project_id = os.getenv("PROJECT_ID")
                except Exception:
                    project_id = os.getenv("PROJECT_ID")

                schemas = ["identity", "kyc", "ledger", "cards", "operations", "origination", "audit", "admin", "catalog", "ref_data", "merchants"]
                reset_schemas = [s for s in schemas if s != "admin"]
                sa_names = ["banking-service-sa", "kyc-service-sa", "ledger-service-sa"]
                roles = [f"{sa}@{project_id}.iam" if project_id and str(project_id) != "None" else sa for sa in sa_names]
                reset_sa_names = ["banking-db-reset-sa"]
                reset_roles = [f"{sa}@{project_id}.iam" if project_id and str(project_id) != "None" else sa for sa in reset_sa_names]
                if os.getenv("IAM_DBA_USERS"):
                    roles.extend([u.strip() for u in os.getenv("IAM_DBA_USERS").split(",") if u.strip()])

                viewer_roles = []
                if os.getenv("IAM_DB_VIEWER_USERS"):
                    viewer_roles.extend([u.strip() for u in os.getenv("IAM_DB_VIEWER_USERS").split(",") if u.strip()])

                # Cloud SQL IAM database users are Terraform-owned. Do not
                # pre-create their backing PostgreSQL roles here, or a service
                # deployment/migration can race Terraform and leave an orphan
                # role that blocks google_sql_user creation.
                bootstrap_roles = [
                    role for role in roles + viewer_roles + reset_roles
                    if "@" not in role
                ]
                for role in bootstrap_roles:
                    try:
                        with connection.begin_nested():
                            stmt = f'DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = \'{role}\') THEN CREATE ROLE "{role}" NOLOGIN; END IF; END $$;'
                            connection.execute(sa.text(stmt))
                    except Exception as role_err:
                        logger.debug(f"Notice: Could not bootstrap role {role}: {role_err}")

                for role in roles:
                    if role.startswith("kyc-service-sa"):
                        allowed_schemas = ["kyc", "identity", "ref_data", "merchants"]
                    elif role.startswith("ledger-service-sa"):
                        allowed_schemas = ["ledger", "audit", "catalog", "ref_data", "merchants"]
                    elif role.startswith("banking-service-sa"):
                        allowed_schemas = [
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
                        ]
                    else:
                        allowed_schemas = schemas

                    for s in allowed_schemas:
                        try:
                            with connection.begin_nested():
                                connection.execute(sa.text(f'GRANT USAGE ON SCHEMA {s} TO "{role}";'))
                                connection.execute(sa.text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {s} TO "{role}";'))
                                connection.execute(sa.text(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {s} GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{role}";'))
                        except Exception as grant_err:
                            logger.debug(f"Notice: Could not grant permissions on {s} to {role}: {grant_err}")

                for role in viewer_roles:
                    for s in reset_schemas:
                        try:
                            with connection.begin_nested():
                                connection.execute(sa.text(f'GRANT USAGE ON SCHEMA {s} TO "{role}";'))
                                connection.execute(sa.text(f'GRANT SELECT ON ALL TABLES IN SCHEMA {s} TO "{role}";'))
                                connection.execute(sa.text(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {s} GRANT SELECT ON TABLES TO "{role}";'))
                        except Exception as grant_err:
                            logger.debug(f"Notice: Could not grant viewer permissions on {s} to {role}: {grant_err}")

                cdc_replication_user = os.getenv("CDC_REPLICATION_USER", "banking_bq_connector")
                require_cdc_bootstrap = os.getenv("REQUIRE_CDC_BOOTSTRAP", "").lower() in {"1", "true", "yes", "on"}
                cdc_schemas = ["cards", "origination", "identity", "kyc", "merchants", "operations"]
                try:
                    cdc_user_exists = connection.execute(
                        sa.text("SELECT 1 FROM pg_roles WHERE rolname = :username"),
                        {"username": cdc_replication_user},
                    ).scalar()
                    if not cdc_user_exists:
                        raise RuntimeError(f"CDC replication user '{cdc_replication_user}' does not exist.")

                    with connection.begin_nested():
                        connection.execute(sa.text(f'ALTER ROLE "{cdc_replication_user}" WITH REPLICATION;'))

                    current_database = connection.execute(sa.text("SELECT current_database()")).scalar()
                    with connection.begin_nested():
                        connection.execute(sa.text(f'GRANT CONNECT ON DATABASE "{current_database}" TO "{cdc_replication_user}";'))

                    for s in cdc_schemas:
                        with connection.begin_nested():
                            connection.execute(sa.text(f'GRANT USAGE ON SCHEMA {s} TO "{cdc_replication_user}";'))
                            connection.execute(sa.text(f'GRANT SELECT ON ALL TABLES IN SCHEMA {s} TO "{cdc_replication_user}";'))
                            connection.execute(sa.text(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {s} GRANT SELECT ON TABLES TO "{cdc_replication_user}";'))
                except Exception as cdc_grant_err:
                    if require_cdc_bootstrap:
                        raise
                    logger.debug(f"Notice: Could not apply CDC grants to {cdc_replication_user}: {cdc_grant_err}")

                current_database = connection.execute(sa.text("SELECT current_database()")).scalar()
                for role in reset_roles:
                    try:
                        with connection.begin_nested():
                            connection.execute(sa.text(f'GRANT CONNECT ON DATABASE "{current_database}" TO "{role}";'))
                    except Exception as grant_err:
                        logger.debug(f"Notice: Could not grant reset database connection to {role}: {grant_err}")

                    for s in schemas:
                        try:
                            with connection.begin_nested():
                                connection.execute(sa.text(f'GRANT USAGE ON SCHEMA {s} TO "{role}";'))
                                connection.execute(sa.text(f'GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA {s} TO "{role}";'))
                                connection.execute(sa.text(f'GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA {s} TO "{role}";'))
                                connection.execute(sa.text(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {s} GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO "{role}";'))
                                connection.execute(sa.text(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {s} GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO "{role}";'))
                        except Exception as grant_err:
                            logger.debug(f"Notice: Could not grant reset permissions on {s} to {role}: {grant_err}")

                immutable_ledger_roles = set(roles + viewer_roles)
                for role in immutable_ledger_roles:
                    try:
                        with connection.begin_nested():
                            connection.execute(sa.text(f'REVOKE UPDATE, DELETE ON TABLE ledger.account_ledger FROM "{role}";'))
                    except Exception as rev_err:
                        logger.debug(f"Notice: Could not revoke immutable ledger permissions from {role}: {rev_err}")

                try:
                    with connection.begin_nested():
                        connection.execute(sa.text('REVOKE UPDATE, DELETE ON TABLE ledger.account_ledger FROM PUBLIC;'))
                except Exception as rev_err:
                    logger.debug(f"Notice: Could not revoke immutable ledger permissions from PUBLIC: {rev_err}")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
