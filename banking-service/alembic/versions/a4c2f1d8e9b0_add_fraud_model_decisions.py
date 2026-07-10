"""add fraud model decisions

Revision ID: a4c2f1d8e9b0
Revises: 2b1c9a7d4e63
Create Date: 2026-07-10 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import utils.database


# revision identifiers, used by Alembic.
revision: str = "a4c2f1d8e9b0"
down_revision: Union[str, Sequence[str], None] = "2b1c9a7d4e63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "fraud_model_decisions",
        sa.Column("id", utils.database.UniversalUUID(), nullable=False),
        sa.Column("authorization_id", utils.database.UniversalUUID(), nullable=False),
        sa.Column("customer_id", utils.database.UniversalUUID(), nullable=False),
        sa.Column("credit_account_id", utils.database.UniversalUUID(), nullable=False),
        sa.Column("card_id", utils.database.UniversalUUID(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("threshold", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("reason_codes", sa.JSON(), nullable=False),
        sa.Column("feature_snapshot", sa.JSON(), nullable=False),
        sa.Column("merchant_name", sa.String(length=255), nullable=True),
        sa.Column("merchant_category_code", sa.String(length=4), nullable=True),
        sa.Column("transaction_channel", sa.String(length=32), nullable=True),
        sa.Column("merchant_country_code", sa.String(length=3), nullable=True),
        sa.Column("merchant_city", sa.String(length=100), nullable=True),
        sa.Column("merchant_region", sa.String(length=100), nullable=True),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("authorization_id", name="uq_fraud_model_decisions_authorization"),
        schema="operations",
    )
    op.create_index(
        "idx_fraud_model_decisions_account_created",
        "fraud_model_decisions",
        ["credit_account_id", "created_at"],
        unique=False,
        schema="operations",
    )
    op.create_index(
        "idx_fraud_model_decisions_card_created",
        "fraud_model_decisions",
        ["card_id", "created_at"],
        unique=False,
        schema="operations",
    )
    op.create_index(
        "idx_fraud_model_decisions_customer_created",
        "fraud_model_decisions",
        ["customer_id", "created_at"],
        unique=False,
        schema="operations",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_fraud_model_decisions_customer_created", table_name="fraud_model_decisions", schema="operations")
    op.drop_index("idx_fraud_model_decisions_card_created", table_name="fraud_model_decisions", schema="operations")
    op.drop_index("idx_fraud_model_decisions_account_created", table_name="fraud_model_decisions", schema="operations")
    op.drop_table("fraud_model_decisions", schema="operations")
