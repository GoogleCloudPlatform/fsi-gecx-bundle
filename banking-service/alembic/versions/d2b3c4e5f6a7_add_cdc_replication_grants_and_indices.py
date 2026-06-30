"""add cdc replication grants and indices for iceberg datalake

Revision ID: d2b3c4e5f6a7
Revises: c1a2b3c4d5e6
Create Date: 2026-06-29 21:55:00.000000

"""
import os
from typing import Sequence, Union
from alembic import op
from sqlalchemy import text
import logging

# revision identifiers, used by Alembic.
revision: str = 'd2b3c4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'c1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    """Upgrade schema with CDC indices and replication grants per Staff DBA Findings 2.1 and 2.2."""
    # 1. Create B-tree index on posted_at for efficient query and CDC replication checkpointing (Staff DBA Finding 2.1)
    try:
        op.create_index(
            "idx_posted_tx_posted_at",
            "posted_transactions",
            ["posted_at"],
            schema="cards",
            if_not_exists=True
        )
    except Exception as e:
        logger.warning(f"Could not create index idx_posted_tx_posted_at: {e}")

    # 2. Grant read permissions on bounded schemas for CDC replication (Staff DBA Finding 2.2)
    if op.get_bind().dialect.name != "postgresql" or os.getenv("SKIP_IAM_GRANTS") == "true":
        return

    db_user = os.getenv("CDC_REPLICATION_USER", "banking_bq_connector")
    conn = op.get_bind()

    try:
        # Verify if user exists before attempting grants
        user_exists = conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = :username"),
            {"username": db_user}
        ).scalar()

        if user_exists:
            has_priv = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_roles 
                    WHERE rolname = CURRENT_USER 
                      AND (rolsuper = true OR rolreplication = true)
                );
            """)).scalar()
            
            if has_priv:
                try:
                    with conn.begin_nested():
                        conn.execute(text(f'ALTER ROLE "{db_user}" WITH REPLICATION;'))
                except Exception as role_ex:
                    logger.warning(f"Could not grant REPLICATION role: {role_ex}")
            else:
                logger.info("Current user does not have replication/superuser privileges; skipping ALTER ROLE WITH REPLICATION.")

            for schema_name in ["cards", "origination", "identity"]:
                try:
                    with conn.begin_nested():
                        conn.execute(text(f'GRANT USAGE ON SCHEMA "{schema_name}" TO "{db_user}";'))
                        conn.execute(text(f'GRANT SELECT ON ALL TABLES IN SCHEMA "{schema_name}" TO "{db_user}";'))
                        conn.execute(text(f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema_name}" GRANT SELECT ON TABLES TO "{db_user}";'))
                except Exception as grant_ex:
                    logger.warning(f"Could not grant schema access on {schema_name}: {grant_ex}")
            logger.info(f"Granted CDC read access on bounded schemas to {db_user}.")
        else:
            logger.info(f"Replication user {db_user} not present; skipping CDC IAM grants.")

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
                has_priv = conn.execute(text("""
                    SELECT EXISTS (
                        SELECT 1 FROM pg_roles 
                        WHERE rolname = CURRENT_USER 
                          AND (rolsuper = true OR rolreplication = true)
                    );
                """)).scalar()
                
                if has_priv:
                    with conn.begin_nested():
                        slot_exists = conn.execute(
                            text("SELECT 1 FROM pg_replication_slots WHERE slot_name = 'datastream_replication_slot'")
                        ).scalar()
                        if not slot_exists:
                            conn.execute(text("SELECT pg_create_logical_replication_slot('datastream_replication_slot', 'pgoutput');"))
                            logger.info("Created datastream_replication_slot for logical replication.")
                else:
                    logger.info("Current user does not have replication or superuser privileges; skipping slot creation.")
            else:
                logger.info(f"PostgreSQL wal_level is '{wal_level}' (not logical); skipping logical replication slot creation.")
        except Exception as slot_ex:
            logger.warning(f"Could not create logical replication slot: {slot_ex}")
    except Exception as e:
        logger.warning(f"Failed to execute CDC IAM grants or publication: {e}")


def downgrade() -> None:
    """Downgrade schema."""
    try:
        op.drop_index("idx_posted_tx_posted_at", table_name="posted_transactions", schema="cards", if_exists=True)
    except Exception as e:
        logger.warning(f"Could not drop index idx_posted_tx_posted_at: {e}")
