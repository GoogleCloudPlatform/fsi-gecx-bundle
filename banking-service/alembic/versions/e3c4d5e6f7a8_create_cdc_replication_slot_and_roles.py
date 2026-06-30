"""create cdc replication slot and roles

Revision ID: e3c4d5e6f7a8
Revises: d2b3c4e5f6a7
Create Date: 2026-06-30 09:15:00.000000

"""
import os
from typing import Sequence, Union
from alembic import op
from sqlalchemy import text
import logging

revision: str = 'e3c4d5e6f7a8'
down_revision: Union[str, Sequence[str], None] = 'd2b3c4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    """Upgrade schema by creating logical replication slot and granting replication role."""
    db_user = os.getenv("CDC_REPLICATION_USER", "banking_bq_connector")
    conn = op.get_bind()

    try:
        user_exists = conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = :username"),
            {"username": db_user}
        ).scalar()

        if user_exists:
            try:
                with conn.begin_nested():
                    conn.execute(text(f'ALTER ROLE "{db_user}" WITH REPLICATION;'))
            except Exception as role_ex:
                logger.warning(f"Could not grant REPLICATION role: {role_ex}")

            for schema_name in ["cards", "origination", "identity"]:
                try:
                    with conn.begin_nested():
                        conn.execute(text(f'GRANT USAGE ON SCHEMA "{schema_name}" TO "{db_user}";'))
                        conn.execute(text(f'GRANT SELECT ON ALL TABLES IN SCHEMA "{schema_name}" TO "{db_user}";'))
                        conn.execute(text(f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema_name}" GRANT SELECT ON TABLES TO "{db_user}";'))
                except Exception as grant_ex:
                    logger.warning(f"Could not grant schema access on {schema_name}: {grant_ex}")
            logger.info(f"Granted CDC read access and REPLICATION role on bounded schemas to {db_user}.")

        # Create publication for Datastream CDC replication
        try:
            with conn.begin_nested():
                pub_exists = conn.execute(
                    text("SELECT 1 FROM pg_publication WHERE pubname = 'datastream_publication'")
                ).scalar()
                if not pub_exists:
                    conn.execute(text('CREATE PUBLICATION datastream_publication FOR ALL TABLES;'))
                    logger.info("Created datastream_publication for logical replication.")
        except Exception as pub_ex:
            logger.warning(f"Could not create publication: {pub_ex}")

        # Check PostgreSQL wal_level before attempting replication slot creation
        try:
            wal_level = conn.execute(text("SHOW wal_level;")).scalar()
            if wal_level == 'logical':
                with conn.begin_nested():
                    slot_exists = conn.execute(
                        text("SELECT 1 FROM pg_replication_slots WHERE slot_name = 'datastream_replication_slot'")
                    ).scalar()
                    if not slot_exists:
                        conn.execute(text("SELECT pg_create_logical_replication_slot('datastream_replication_slot', 'pgoutput');"))
                        logger.info("Created datastream_replication_slot for logical replication.")
            else:
                logger.info(f"PostgreSQL wal_level is '{wal_level}' (not logical); skipping logical replication slot creation.")
        except Exception as slot_ex:
            logger.warning(f"Could not create logical replication slot: {slot_ex}")
    except Exception as e:
        logger.warning(f"Failed to execute CDC IAM grants or replication slot creation: {e}")


def downgrade() -> None:
    """Downgrade schema by dropping logical replication slot."""
    conn = op.get_bind()
    try:
        wal_level = conn.execute(text("SHOW wal_level;")).scalar()
        if wal_level == 'logical':
            with conn.begin_nested():
                conn.execute(text("SELECT pg_drop_replication_slot('datastream_replication_slot') WHERE EXISTS (SELECT 1 FROM pg_replication_slots WHERE slot_name = 'datastream_replication_slot');"))
    except Exception as e:
        logger.warning(f"Failed to drop logical replication slot: {e}")
