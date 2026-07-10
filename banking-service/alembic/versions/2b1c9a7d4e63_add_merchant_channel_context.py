"""add merchant channel context

Revision ID: 2b1c9a7d4e63
Revises: 5f4d2c1a8b90
Create Date: 2026-07-10 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2b1c9a7d4e63"
down_revision: Union[str, Sequence[str], None] = "5f4d2c1a8b90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("merchant_stores", sa.Column("city", sa.String(length=100), nullable=True), schema="merchants")
    op.add_column("merchant_stores", sa.Column("region", sa.String(length=100), nullable=True), schema="merchants")
    op.add_column("merchant_stores", sa.Column("postal_code", sa.String(length=20), nullable=True), schema="merchants")
    op.add_column("merchant_stores", sa.Column("latitude", sa.Numeric(9, 6), nullable=True), schema="merchants")
    op.add_column("merchant_stores", sa.Column("longitude", sa.Numeric(9, 6), nullable=True), schema="merchants")
    op.add_column("merchant_stores", sa.Column("card_present_capable", sa.Boolean(), nullable=False, server_default=sa.true()), schema="merchants")
    op.add_column("merchant_stores", sa.Column("ecommerce_capable", sa.Boolean(), nullable=False, server_default=sa.false()), schema="merchants")
    op.add_column("merchant_stores", sa.Column("high_risk_flags", sa.String(length=255), nullable=True), schema="merchants")

    op.add_column("transaction_authorization", sa.Column("transaction_channel", sa.String(length=32), nullable=True), schema="cards")
    op.add_column("transaction_authorization", sa.Column("entry_mode", sa.String(length=32), nullable=True), schema="cards")
    op.add_column("transaction_authorization", sa.Column("merchant_country_code", sa.String(length=3), nullable=True), schema="cards")
    op.add_column("transaction_authorization", sa.Column("merchant_city", sa.String(length=100), nullable=True), schema="cards")
    op.add_column("transaction_authorization", sa.Column("merchant_region", sa.String(length=100), nullable=True), schema="cards")
    op.add_column("transaction_authorization", sa.Column("merchant_postal_code", sa.String(length=20), nullable=True), schema="cards")
    op.add_column("transaction_authorization", sa.Column("merchant_latitude", sa.Numeric(9, 6), nullable=True), schema="cards")
    op.add_column("transaction_authorization", sa.Column("merchant_longitude", sa.Numeric(9, 6), nullable=True), schema="cards")
    op.add_column("transaction_authorization", sa.Column("ip_country_code", sa.String(length=3), nullable=True), schema="cards")
    op.add_column("transaction_authorization", sa.Column("shipping_country_code", sa.String(length=3), nullable=True), schema="cards")
    op.add_column("transaction_authorization", sa.Column("is_digital_goods", sa.Boolean(), nullable=False, server_default=sa.false()), schema="cards")

    op.alter_column("merchant_stores", "card_present_capable", server_default=None, schema="merchants")
    op.alter_column("merchant_stores", "ecommerce_capable", server_default=None, schema="merchants")
    op.alter_column("transaction_authorization", "is_digital_goods", server_default=None, schema="cards")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("transaction_authorization", "is_digital_goods", schema="cards")
    op.drop_column("transaction_authorization", "shipping_country_code", schema="cards")
    op.drop_column("transaction_authorization", "ip_country_code", schema="cards")
    op.drop_column("transaction_authorization", "merchant_longitude", schema="cards")
    op.drop_column("transaction_authorization", "merchant_latitude", schema="cards")
    op.drop_column("transaction_authorization", "merchant_postal_code", schema="cards")
    op.drop_column("transaction_authorization", "merchant_region", schema="cards")
    op.drop_column("transaction_authorization", "merchant_city", schema="cards")
    op.drop_column("transaction_authorization", "merchant_country_code", schema="cards")
    op.drop_column("transaction_authorization", "entry_mode", schema="cards")
    op.drop_column("transaction_authorization", "transaction_channel", schema="cards")

    op.drop_column("merchant_stores", "high_risk_flags", schema="merchants")
    op.drop_column("merchant_stores", "ecommerce_capable", schema="merchants")
    op.drop_column("merchant_stores", "card_present_capable", schema="merchants")
    op.drop_column("merchant_stores", "longitude", schema="merchants")
    op.drop_column("merchant_stores", "latitude", schema="merchants")
    op.drop_column("merchant_stores", "postal_code", schema="merchants")
    op.drop_column("merchant_stores", "region", schema="merchants")
    op.drop_column("merchant_stores", "city", schema="merchants")
