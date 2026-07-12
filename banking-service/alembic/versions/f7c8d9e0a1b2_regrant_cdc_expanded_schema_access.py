"""regrant CDC expanded schema access

Revision ID: f7c8d9e0a1b2
Revises: c2f3e4d5a6b7
Create Date: 2026-07-12 23:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import os


revision: str = "f7c8d9e0a1b2"
down_revision: Union[str, Sequence[str], None] = "c2f3e4d5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql" or os.getenv("SKIP_IAM_GRANTS") == "true":
        return

    cdc_user = os.getenv("CDC_REPLICATION_USER", "banking_bq_connector")
    for schema_name in CDC_SCHEMAS:
        op.execute(
            f"DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{cdc_user}') THEN "
            f'GRANT USAGE ON SCHEMA {schema_name} TO "{cdc_user}"; '
            f'GRANT SELECT ON ALL TABLES IN SCHEMA {schema_name} TO "{cdc_user}"; '
            f'ALTER DEFAULT PRIVILEGES IN SCHEMA {schema_name} GRANT SELECT ON TABLES TO "{cdc_user}"; '
            "END IF; END $$;"
        )


def downgrade() -> None:
    pass

