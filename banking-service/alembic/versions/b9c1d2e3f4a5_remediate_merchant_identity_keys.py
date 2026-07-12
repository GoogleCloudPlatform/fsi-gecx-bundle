"""remediate merchant identity keys

Revision ID: b9c1d2e3f4a5
Revises: e6f7a8b9c0d1
Create Date: 2026-07-12 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import utils.database


# revision identifiers, used by Alembic.
revision: str = "b9c1d2e3f4a5"
down_revision: Union[str, Sequence[str], None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
REMEDIATION_MARKER = "remediated_by:b9c1d2e3f4a5"


def upgrade() -> None:
    """Make merchant_id a UUID identity and move the prior slug into merchant_slug."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    master_columns = {column["name"] for column in inspector.get_columns("merchant_master", schema="merchants")}
    auth_columns = {column["name"] for column in inspector.get_columns("transaction_authorization", schema="cards")}

    if "merchant_id" in master_columns:
        op.execute("DELETE FROM merchants.merchant_stores")
        op.execute("DELETE FROM merchants.merchant_master")

        op.execute("ALTER TABLE merchants.merchant_stores DROP CONSTRAINT IF EXISTS merchant_stores_merchant_id_fkey")
        op.execute("DROP INDEX IF EXISTS merchants.ix_merchants_merchant_stores_merchant_id")
        op.execute("DROP INDEX IF EXISTS merchants.ix_merchants_merchant_master_merchant_id")

        op.alter_column(
            "merchant_master",
            "merchant_id",
            new_column_name="merchant_slug",
            existing_type=sa.String(length=100),
            existing_nullable=False,
            schema="merchants",
        )
        op.execute(f"COMMENT ON COLUMN merchants.merchant_master.merchant_slug IS '{REMEDIATION_MARKER}'")
        op.drop_column("merchant_stores", "merchant_id", schema="merchants")
        op.add_column(
            "merchant_stores",
            sa.Column("merchant_id", utils.database.UniversalUUID(), nullable=False),
            schema="merchants",
        )

        op.create_index(
            op.f("ix_merchants_merchant_master_merchant_slug"),
            "merchant_master",
            ["merchant_slug"],
            unique=True,
            schema="merchants",
        )
        op.create_index(
            op.f("ix_merchants_merchant_stores_merchant_id"),
            "merchant_stores",
            ["merchant_id"],
            unique=False,
            schema="merchants",
        )
        op.create_foreign_key(
            "merchant_stores_merchant_id_fkey",
            "merchant_stores",
            "merchant_master",
            ["merchant_id"],
            ["id"],
            source_schema="merchants",
            referent_schema="merchants",
            ondelete="CASCADE",
        )

    if "merchant_id" not in auth_columns:
        op.add_column("transaction_authorization", sa.Column("merchant_id", utils.database.UniversalUUID(), nullable=True), schema="cards")
        op.create_foreign_key(
            "transaction_authorization_merchant_id_fkey",
            "transaction_authorization",
            "merchant_master",
            ["merchant_id"],
            ["id"],
            source_schema="cards",
            referent_schema="merchants",
            ondelete="SET NULL",
        )
    if "merchant_store_id" not in auth_columns:
        op.add_column("transaction_authorization", sa.Column("merchant_store_id", utils.database.UniversalUUID(), nullable=True), schema="cards")
        op.create_foreign_key(
            "transaction_authorization_merchant_store_id_fkey",
            "transaction_authorization",
            "merchant_stores",
            ["merchant_store_id"],
            ["id"],
            source_schema="cards",
            referent_schema="merchants",
            ondelete="SET NULL",
        )
    if "merchant_slug" not in auth_columns:
        op.add_column("transaction_authorization", sa.Column("merchant_slug", sa.String(length=100), nullable=True), schema="cards")


def downgrade() -> None:
    """Restore prior slug-based merchant_id relationship. Destructive for merchant refs."""
    bind = op.get_bind()
    marker = bind.execute(
        sa.text(
            """
            SELECT col_description('merchants.merchant_master'::regclass, ordinal_position)
            FROM information_schema.columns
            WHERE table_schema = 'merchants'
              AND table_name = 'merchant_master'
              AND column_name = 'merchant_slug'
            """
        )
    ).scalar()
    if marker != REMEDIATION_MARKER:
        return

    op.drop_constraint("transaction_authorization_merchant_store_id_fkey", "transaction_authorization", schema="cards", type_="foreignkey")
    op.drop_constraint("transaction_authorization_merchant_id_fkey", "transaction_authorization", schema="cards", type_="foreignkey")
    op.drop_column("transaction_authorization", "merchant_slug", schema="cards")
    op.drop_column("transaction_authorization", "merchant_store_id", schema="cards")
    op.drop_column("transaction_authorization", "merchant_id", schema="cards")

    op.execute("DELETE FROM merchants.merchant_stores")
    op.execute("DELETE FROM merchants.merchant_master")

    op.drop_constraint("merchant_stores_merchant_id_fkey", "merchant_stores", schema="merchants", type_="foreignkey")
    op.drop_index(op.f("ix_merchants_merchant_stores_merchant_id"), table_name="merchant_stores", schema="merchants")
    op.drop_index(op.f("ix_merchants_merchant_master_merchant_slug"), table_name="merchant_master", schema="merchants")

    op.drop_column("merchant_stores", "merchant_id", schema="merchants")
    op.add_column(
        "merchant_stores",
        sa.Column("merchant_id", sa.String(length=100), nullable=False),
        schema="merchants",
    )
    op.alter_column(
        "merchant_master",
        "merchant_slug",
        new_column_name="merchant_id",
        existing_type=sa.String(length=100),
        existing_nullable=False,
        schema="merchants",
    )
    op.execute("COMMENT ON COLUMN merchants.merchant_master.merchant_id IS NULL")

    op.create_index(
        op.f("ix_merchants_merchant_master_merchant_id"),
        "merchant_master",
        ["merchant_id"],
        unique=True,
        schema="merchants",
    )
    op.create_index(
        op.f("ix_merchants_merchant_stores_merchant_id"),
        "merchant_stores",
        ["merchant_id"],
        unique=False,
        schema="merchants",
    )
    op.create_foreign_key(
        "merchant_stores_merchant_id_fkey",
        "merchant_stores",
        "merchant_master",
        ["merchant_id"],
        ["merchant_id"],
        source_schema="merchants",
        referent_schema="merchants",
        ondelete="CASCADE",
    )
