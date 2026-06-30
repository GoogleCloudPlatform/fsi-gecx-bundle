"""add_credit_scoring_and_account_product_types

Revision ID: 90b69c563699
Revises: e3c4d5e6f7a8
Create Date: 2026-06-30 11:04:03.712295

"""
import os
import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '90b69c563699'
down_revision: Union[str, Sequence[str], None] = 'e3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger(__name__)


def upgrade() -> None:
    conn = op.get_bind()

    # 0. Create schema catalog
    logger.info("Creating schema catalog")
    if conn.dialect.name == "postgresql":
        with conn.begin_nested():
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS catalog;"))

    # 1. Create table catalog.credit_products
    logger.info("Creating table catalog.credit_products")
    with conn.begin_nested():
        op.create_table(
            'credit_products',
            sa.Column('product_code', sa.String(length=50), nullable=False),
            sa.Column('product_name', sa.String(length=100), nullable=False),
            sa.Column('min_credit_limit_cents', sa.BigInteger(), nullable=False),
            sa.Column('max_credit_limit_cents', sa.BigInteger(), nullable=False),
            sa.Column('purchase_apr', sa.Numeric(precision=5, scale=4), nullable=False),
            sa.Column('cashback_rate', sa.Numeric(precision=5, scale=4), nullable=False, server_default='0.0000'),
            sa.Column('travel_multiplier', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('dining_multiplier', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('annual_fee_cents', sa.BigInteger(), nullable=False, server_default='0'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint('product_code'),
            schema='catalog'
        )

    # 2. Create table catalog.deposit_products
    logger.info("Creating table catalog.deposit_products")
    with conn.begin_nested():
        op.create_table(
            'deposit_products',
            sa.Column('product_code', sa.String(length=50), nullable=False),
            sa.Column('product_name', sa.String(length=100), nullable=False),
            sa.Column('annual_percentage_yield', sa.Numeric(precision=5, scale=4), nullable=False, server_default='0.0000'),
            sa.Column('monthly_maintenance_fee_cents', sa.BigInteger(), nullable=False, server_default='0'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint('product_code'),
            schema='catalog'
        )

    # 3. Create table kyc.user_credit_profiles
    logger.info("Creating table kyc.user_credit_profiles")
    with conn.begin_nested():
        op.create_table(
            'user_credit_profiles',
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('user_id', sa.UUID(), nullable=False),
            sa.Column('credit_score', sa.Integer(), nullable=False),
            sa.Column('credit_tier', sa.String(length=50), nullable=False),
            sa.Column('stated_annual_income_cents', sa.BigInteger(), nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['user_id'], ['identity.users.id'], ondelete='CASCADE'),
            sa.UniqueConstraint('user_id'),
            schema='kyc'
        )

    # 4. Seed credit_products
    logger.info("Seeding credit_products")
    credit_products_table = sa.table(
        'credit_products',
        sa.column('product_code', sa.String),
        sa.column('product_name', sa.String),
        sa.column('min_credit_limit_cents', sa.BigInteger),
        sa.column('max_credit_limit_cents', sa.BigInteger),
        sa.column('purchase_apr', sa.Numeric),
        sa.column('cashback_rate', sa.Numeric),
        sa.column('travel_multiplier', sa.Integer),
        sa.column('dining_multiplier', sa.Integer),
        sa.column('annual_fee_cents', sa.BigInteger),
        sa.column('is_active', sa.Boolean),
        schema='catalog'
    )
    with conn.begin_nested():
        op.bulk_insert(credit_products_table, [
            {
                'product_code': 'PLATINUM_TRAVEL_REWARDS',
                'product_name': 'Nova Platinum Travel',
                'min_credit_limit_cents': 1500000,
                'max_credit_limit_cents': 10000000,
                'purchase_apr': 0.1899,
                'cashback_rate': 0.0000,
                'travel_multiplier': 3,
                'dining_multiplier': 3,
                'annual_fee_cents': 9500,
                'is_active': True
            },
            {
                'product_code': 'CASHBACK_EVERYDAY',
                'product_name': 'Nova Cashback Everyday',
                'min_credit_limit_cents': 300000,
                'max_credit_limit_cents': 1500000,
                'purchase_apr': 0.2199,
                'cashback_rate': 0.0150,
                'travel_multiplier': 1,
                'dining_multiplier': 1,
                'annual_fee_cents': 0,
                'is_active': True
            },
            {
                'product_code': 'BUSINESS_ADVANTAGE',
                'product_name': 'Executive Business Advantage',
                'min_credit_limit_cents': 2000000,
                'max_credit_limit_cents': 15000000,
                'purchase_apr': 0.1799,
                'cashback_rate': 0.0200,
                'travel_multiplier': 2,
                'dining_multiplier': 2,
                'annual_fee_cents': 0,
                'is_active': True
            },
            {
                'product_code': 'SECURED_STARTER',
                'product_name': 'Nova Secured Rebuilder',
                'min_credit_limit_cents': 50000,
                'max_credit_limit_cents': 250000,
                'purchase_apr': 0.2799,
                'cashback_rate': 0.0100,
                'travel_multiplier': 1,
                'dining_multiplier': 1,
                'annual_fee_cents': 0,
                'is_active': True
            }
        ])

    # 5. Seed deposit_products
    logger.info("Seeding deposit_products")
    deposit_products_table = sa.table(
        'deposit_products',
        sa.column('product_code', sa.String),
        sa.column('product_name', sa.String),
        sa.column('annual_percentage_yield', sa.Numeric),
        sa.column('monthly_maintenance_fee_cents', sa.BigInteger),
        sa.column('is_active', sa.Boolean),
        schema='catalog'
    )
    with conn.begin_nested():
        op.bulk_insert(deposit_products_table, [
            {
                'product_code': 'CHECKING_SIGNATURE',
                'product_name': 'Nova Signature Checking',
                'annual_percentage_yield': 0.0005,
                'monthly_maintenance_fee_cents': 1500,
                'is_active': True
            },
            {
                'product_code': 'CHECKING_EVERYDAY',
                'product_name': 'Nova Everyday Checking',
                'annual_percentage_yield': 0.0000,
                'monthly_maintenance_fee_cents': 0,
                'is_active': True
            },
            {
                'product_code': 'SAVINGS_HIGH_YIELD',
                'product_name': 'Nova High Yield Savings',
                'annual_percentage_yield': 0.0450,
                'monthly_maintenance_fee_cents': 0,
                'is_active': True
            },
            {
                'product_code': 'BUSINESS_CHECKING',
                'product_name': 'Nova Business Checking',
                'annual_percentage_yield': 0.0010,
                'monthly_maintenance_fee_cents': 1000,
                'is_active': True
            }
        ])

    # 6. Add columns to ledger.accounts
    logger.info("Adding columns to ledger.accounts")
    with conn.begin_nested():
        op.add_column('accounts', sa.Column('product_code', sa.String(length=50), nullable=False, server_default='CHECKING_EVERYDAY'), schema='ledger')
        op.add_column('accounts', sa.Column('routing_number', sa.String(length=9), nullable=False, server_default='021000021'), schema='ledger')
        op.create_foreign_key('fk_accounts_deposit_products', 'accounts', 'deposit_products', ['product_code'], ['product_code'], source_schema='ledger', referent_schema='catalog', ondelete='RESTRICT')
        # Index foreign key to avoid full table scans on joins
        op.create_index('idx_accounts_product_code', 'accounts', ['product_code'], schema='ledger')

    # 7. Add product_code column to cards.credit_accounts
    logger.info("Adding columns to cards.credit_accounts")
    with conn.begin_nested():
        op.add_column('credit_accounts', sa.Column('product_code', sa.String(length=50), nullable=False, server_default='CASHBACK_EVERYDAY'), schema='cards')
        op.create_foreign_key('fk_credit_accounts_credit_products', 'credit_accounts', 'credit_products', ['product_code'], ['product_code'], source_schema='cards', referent_schema='catalog', ondelete='RESTRICT')
        # Index foreign key
        op.create_index('idx_credit_accounts_product_code', 'credit_accounts', ['product_code'], schema='cards')

    # 8. Alter customer_id type to UUID in cards.credit_accounts and add foreign key
    if conn.dialect.name == "postgresql":
        logger.info("Cleaning up customer_id values in cards.credit_accounts before altering type to UUID")
        with conn.begin_nested():
            conn.execute(text("""
                UPDATE cards.credit_accounts ca
                SET customer_id = CAST(u.id AS varchar)
                FROM identity.users u
                WHERE ca.customer_id = u.auth_provider_uid;
            """))
            conn.execute(text("""
                DELETE FROM cards.posted_transactions
                WHERE account_id IN (
                    SELECT id FROM cards.credit_accounts
                    WHERE customer_id NOT IN (SELECT CAST(id AS varchar) FROM identity.users)
                       OR customer_id IS NULL
                );
            """))
            conn.execute(text("""
                DELETE FROM cards.transaction_authorizations
                WHERE account_id IN (
                    SELECT id FROM cards.credit_accounts
                    WHERE customer_id NOT IN (SELECT CAST(id AS varchar) FROM identity.users)
                       OR customer_id IS NULL
                );
            """))
            conn.execute(text("""
                DELETE FROM cards.issued_card
                WHERE account_id IN (
                    SELECT id FROM cards.credit_accounts
                    WHERE customer_id NOT IN (SELECT CAST(id AS varchar) FROM identity.users)
                       OR customer_id IS NULL
                );
            """))
            conn.execute(text("""
                DELETE FROM cards.credit_accounts
                WHERE customer_id NOT IN (SELECT CAST(id AS varchar) FROM identity.users)
                   OR customer_id IS NULL;
            """))

    logger.info("Altering customer_id column in cards.credit_accounts")
    with conn.begin_nested():
        op.execute(text('ALTER TABLE cards.credit_accounts ALTER COLUMN customer_id TYPE uuid USING customer_id::uuid;'))
        op.create_foreign_key('fk_credit_accounts_users', 'credit_accounts', 'users', ['customer_id'], ['id'], source_schema='cards', referent_schema='identity', ondelete='RESTRICT')
        # Index foreign key
        op.create_index('idx_credit_accounts_customer_id', 'credit_accounts', ['customer_id'], schema='cards')


def downgrade() -> None:
    conn = op.get_bind()

    # 1. Drop foreign keys and columns on cards.credit_accounts
    logger.info("Reverting columns in cards.credit_accounts")
    with conn.begin_nested():
        op.drop_index('idx_credit_accounts_customer_id', table_name='credit_accounts', schema='cards')
        op.drop_index('idx_credit_accounts_product_code', table_name='credit_accounts', schema='cards')
        op.drop_constraint('fk_credit_accounts_users', 'credit_accounts', schema='cards', type_='foreignkey')
        op.drop_constraint('fk_credit_accounts_credit_products', 'credit_accounts', schema='cards', type_='foreignkey')
        op.drop_column('credit_accounts', 'product_code', schema='cards')
        op.execute(text('ALTER TABLE cards.credit_accounts ALTER COLUMN customer_id TYPE varchar(36);'))

    # 2. Drop foreign keys and columns on ledger.accounts
    logger.info("Reverting columns in ledger.accounts")
    with conn.begin_nested():
        op.drop_index('idx_accounts_product_code', table_name='accounts', schema='ledger')
        op.drop_constraint('fk_accounts_deposit_products', 'accounts', schema='ledger', type_='foreignkey')
        op.drop_column('accounts', 'routing_number', schema='ledger')
        op.drop_column('accounts', 'product_code', schema='ledger')

    # 3. Drop tables
    logger.info("Dropping tables")
    with conn.begin_nested():
        op.drop_table('user_credit_profiles', schema='kyc')
        op.drop_table('deposit_products', schema='catalog')
        op.drop_table('credit_products', schema='catalog')

    # 4. Drop schema catalog
    logger.info("Dropping schema catalog")
    if conn.dialect.name == "postgresql":
        with conn.begin_nested():
            conn.execute(text("DROP SCHEMA IF EXISTS catalog;"))
