"""enrich MCC taxonomy

Revision ID: c2f3e4d5a6b7
Revises: b9c1d2e3f4a5
Create Date: 2026-07-12 17:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import utils.database


# revision identifiers, used by Alembic.
revision: str = "c2f3e4d5a6b7"
down_revision: Union[str, Sequence[str], None] = "b9c1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "merchant_category_codes"
SCHEMA = "merchants"


def _columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(TABLE, schema=SCHEMA)}


def upgrade() -> None:
    """Move MCC taxonomy to UUID identity plus enriched columns.

    Existing reference rows are intentionally discarded; full reset/reseed
    repopulates this table from the enriched MCC JSON resource.
    """
    columns = _columns()
    if "id" in columns:
        return

    op.execute(f"DELETE FROM {SCHEMA}.{TABLE}")
    op.add_column(TABLE, sa.Column("id", utils.database.UniversalUUID(), nullable=False), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("ui_label", sa.String(length=100), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("canonical_title", sa.String(length=150), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("canonical_group", sa.String(length=100), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("risk_level", sa.String(length=20), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("risk_score", sa.Integer(), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("spend_type", sa.String(length=50), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("recurrence_likelihood", sa.String(length=20), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("velocity_risk", sa.String(length=20), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("chargeback_prone", sa.Boolean(), nullable=False, server_default=sa.false()), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("is_travel", sa.Boolean(), nullable=False, server_default=sa.false()), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("is_subscription_common", sa.Boolean(), nullable=False, server_default=sa.false()), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("is_luxury", sa.Boolean(), nullable=False, server_default=sa.false()), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("is_essential", sa.Boolean(), nullable=False, server_default=sa.false()), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")), schema=SCHEMA)

    op.drop_index(op.f("ix_merchants_merchant_category_codes_mcc"), table_name=TABLE, schema=SCHEMA)
    op.drop_constraint("merchant_category_codes_pkey", TABLE, schema=SCHEMA, type_="primary")
    op.create_primary_key("merchant_category_codes_pkey", TABLE, ["id"], schema=SCHEMA)
    op.create_index(op.f("ix_merchants_merchant_category_codes_mcc"), TABLE, ["mcc"], unique=True, schema=SCHEMA)

    op.alter_column(TABLE, "chargeback_prone", server_default=None, schema=SCHEMA)
    op.alter_column(TABLE, "is_travel", server_default=None, schema=SCHEMA)
    op.alter_column(TABLE, "is_subscription_common", server_default=None, schema=SCHEMA)
    op.alter_column(TABLE, "is_luxury", server_default=None, schema=SCHEMA)
    op.alter_column(TABLE, "is_essential", server_default=None, schema=SCHEMA)
    op.alter_column(TABLE, "metadata_json", server_default=None, schema=SCHEMA)


def downgrade() -> None:
    columns = _columns()
    if "id" not in columns:
        return

    op.execute(f"DELETE FROM {SCHEMA}.{TABLE}")
    op.drop_index(op.f("ix_merchants_merchant_category_codes_mcc"), table_name=TABLE, schema=SCHEMA)
    op.drop_constraint("merchant_category_codes_pkey", TABLE, schema=SCHEMA, type_="primary")
    op.drop_column(TABLE, "metadata_json", schema=SCHEMA)
    op.drop_column(TABLE, "is_essential", schema=SCHEMA)
    op.drop_column(TABLE, "is_luxury", schema=SCHEMA)
    op.drop_column(TABLE, "is_subscription_common", schema=SCHEMA)
    op.drop_column(TABLE, "is_travel", schema=SCHEMA)
    op.drop_column(TABLE, "chargeback_prone", schema=SCHEMA)
    op.drop_column(TABLE, "velocity_risk", schema=SCHEMA)
    op.drop_column(TABLE, "recurrence_likelihood", schema=SCHEMA)
    op.drop_column(TABLE, "spend_type", schema=SCHEMA)
    op.drop_column(TABLE, "risk_score", schema=SCHEMA)
    op.drop_column(TABLE, "risk_level", schema=SCHEMA)
    op.drop_column(TABLE, "canonical_group", schema=SCHEMA)
    op.drop_column(TABLE, "canonical_title", schema=SCHEMA)
    op.drop_column(TABLE, "ui_label", schema=SCHEMA)
    op.drop_column(TABLE, "id", schema=SCHEMA)
    op.create_primary_key("merchant_category_codes_pkey", TABLE, ["mcc"], schema=SCHEMA)
    op.create_index(op.f("ix_merchants_merchant_category_codes_mcc"), TABLE, ["mcc"], unique=False, schema=SCHEMA)
