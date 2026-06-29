"""migrate legacy tables to dedicated cards and operations schemas

Revision ID: 888d74ebf127
Revises: 2ca894c97a9c
Create Date: 2026-06-27 19:50:07.281350

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '888d74ebf127'
down_revision: Union[str, Sequence[str], None] = '2ca894c97a9c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('financial_account',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('customer_id', sa.String(length=36), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('credit_limit_cents', sa.BigInteger(), nullable=False),
    sa.Column('cleared_balance_cents', sa.BigInteger(), nullable=False),
    sa.Column('available_credit_cents', sa.BigInteger(), nullable=False),
    sa.Column('payment_due_date', sa.DateTime(), nullable=True),
    sa.Column('statement_close_date', sa.DateTime(), nullable=True),
    sa.Column('last_payment_date', sa.DateTime(), nullable=True),
    sa.Column('last_payment_amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=True),
    sa.Column('opened_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema='cards'
    )
    op.create_table('issued_card',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('account_id', sa.UUID(), nullable=False),
    sa.Column('cardholder_name', sa.String(length=150), nullable=False),
    sa.Column('card_token', sa.String(length=255), nullable=False),
    sa.Column('last_four', sa.String(length=4), nullable=False),
    sa.Column('encrypted_pin_block', sa.String(length=255), nullable=True),
    sa.Column('pin_fail_count', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('exp_month', sa.Integer(), nullable=False),
    sa.Column('exp_year', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('is_virtual', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['account_id'], ['cards.financial_account.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('card_token'),
    schema='cards'
    )
    op.create_index(op.f('idx_issued_card_token'), 'issued_card', ['card_token'], unique=1, schema='cards')
    op.create_table('transaction_authorization',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('card_id', sa.UUID(), nullable=False),
    sa.Column('account_id', sa.UUID(), nullable=False),
    sa.Column('transaction_amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('transaction_currency', sa.String(length=3), nullable=False),
    sa.Column('billing_amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('billing_currency', sa.String(length=3), nullable=False),
    sa.Column('exchange_rate', sa.Numeric(precision=18, scale=9), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('decline_reason', sa.String(length=50), nullable=False),
    sa.Column('auth_code', sa.String(length=6), nullable=False),
    sa.Column('retrieval_reference_number', sa.String(length=12), nullable=False),
    sa.Column('card_network', sa.String(length=30), nullable=False),
    sa.Column('merchant_category_code', sa.String(length=4), nullable=False),
    sa.Column('merchant_name', sa.String(length=255), nullable=True),
    sa.Column('fraud_risk_score', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['cards.financial_account.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['card_id'], ['cards.issued_card.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    schema='cards'
    )
    op.create_index(op.f('idx_auth_account_status'), 'transaction_authorization', ['account_id', 'status'], unique=False, schema='cards')
    op.create_table('account_ledger',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('account_id', sa.UUID(), nullable=False),
    sa.Column('authorization_id', sa.UUID(), nullable=True),
    sa.Column('auth_code', sa.String(length=6), nullable=True),
    sa.Column('retrieval_reference_number', sa.String(length=12), nullable=True),
    sa.Column('amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=False),
    sa.Column('posted_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['account_id'], ['cards.financial_account.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['authorization_id'], ['cards.transaction_authorization.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    schema='cards'
    )
    op.create_index(op.f('idx_ledger_account_posted'), 'account_ledger', ['account_id', 'posted_at'], unique=False, schema='cards')
    op.create_index(op.f('idx_ledger_account'), 'account_ledger', ['account_id'], unique=False, schema='cards')
    op.create_table('system_settings',
    sa.Column('key', sa.String(), nullable=False),
    sa.Column('value', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('key'),
    schema='operations'
    )
    op.create_index(op.f('ix_system_settings_key'), 'system_settings', ['key'], unique=False, schema='operations')
    op.create_table('support_escalations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('room_name', sa.String(), nullable=False),
    sa.Column('customer_id', sa.String(), nullable=False),
    sa.Column('reason', sa.String(), nullable=True),
    sa.Column('status', sa.String(), nullable=True),
    sa.Column('transcript', sa.JSON(), nullable=True),
    sa.Column('assigned_to', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema='operations'
    )

    op.drop_table('account_ledger')
    op.drop_table('transaction_authorization')
    op.drop_table('issued_card')
    op.drop_table('financial_account')
    op.drop_table('support_escalations')
    op.drop_index(op.f('ix_system_settings_key'), table_name='system_settings')
    op.drop_table('system_settings')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table('financial_account',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('customer_id', sa.String(length=36), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('credit_limit_cents', sa.BigInteger(), nullable=False),
    sa.Column('cleared_balance_cents', sa.BigInteger(), nullable=False),
    sa.Column('available_credit_cents', sa.BigInteger(), nullable=False),
    sa.Column('payment_due_date', sa.DateTime(), nullable=True),
    sa.Column('statement_close_date', sa.DateTime(), nullable=True),
    sa.Column('last_payment_date', sa.DateTime(), nullable=True),
    sa.Column('last_payment_amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=True),
    sa.Column('opened_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('issued_card',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('account_id', sa.UUID(), nullable=False),
    sa.Column('cardholder_name', sa.String(length=150), nullable=False),
    sa.Column('card_token', sa.String(length=255), nullable=False),
    sa.Column('last_four', sa.String(length=4), nullable=False),
    sa.Column('encrypted_pin_block', sa.String(length=255), nullable=True),
    sa.Column('pin_fail_count', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('exp_month', sa.Integer(), nullable=False),
    sa.Column('exp_year', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('is_virtual', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['account_id'], ['financial_account.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('card_token')
    )
    op.create_index(op.f('idx_issued_card_token'), 'issued_card', ['card_token'], unique=1)
    op.create_table('transaction_authorization',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('card_id', sa.UUID(), nullable=False),
    sa.Column('account_id', sa.UUID(), nullable=False),
    sa.Column('transaction_amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('transaction_currency', sa.String(length=3), nullable=False),
    sa.Column('billing_amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('billing_currency', sa.String(length=3), nullable=False),
    sa.Column('exchange_rate', sa.Numeric(precision=18, scale=9), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('decline_reason', sa.String(length=50), nullable=False),
    sa.Column('auth_code', sa.String(length=6), nullable=False),
    sa.Column('retrieval_reference_number', sa.String(length=12), nullable=False),
    sa.Column('card_network', sa.String(length=30), nullable=False),
    sa.Column('merchant_category_code', sa.String(length=4), nullable=False),
    sa.Column('merchant_name', sa.String(length=255), nullable=True),
    sa.Column('fraud_risk_score', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['financial_account.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['card_id'], ['issued_card.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('idx_auth_account_status'), 'transaction_authorization', ['account_id', 'status'], unique=False)
    op.create_table('account_ledger',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('account_id', sa.UUID(), nullable=False),
    sa.Column('authorization_id', sa.UUID(), nullable=True),
    sa.Column('auth_code', sa.String(length=6), nullable=True),
    sa.Column('retrieval_reference_number', sa.String(length=12), nullable=True),
    sa.Column('amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=False),
    sa.Column('posted_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['account_id'], ['financial_account.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['authorization_id'], ['transaction_authorization.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('idx_ledger_account_posted'), 'account_ledger', ['account_id', 'posted_at'], unique=False)
    op.create_index(op.f('idx_ledger_account'), 'account_ledger', ['account_id'], unique=False)
    op.create_table('system_settings',
    sa.Column('key', sa.String(), nullable=False),
    sa.Column('value', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_index(op.f('ix_system_settings_key'), 'system_settings', ['key'], unique=False)
    op.create_table('support_escalations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('room_name', sa.String(), nullable=False),
    sa.Column('customer_id', sa.String(), nullable=False),
    sa.Column('reason', sa.String(), nullable=True),
    sa.Column('status', sa.String(), nullable=True),
    sa.Column('transcript', sa.JSON(), nullable=True),
    sa.Column('assigned_to', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )

    op.drop_table('account_ledger', schema='cards')
    op.drop_table('transaction_authorization', schema='cards')
    op.drop_table('issued_card', schema='cards')
    op.drop_table('financial_account', schema='cards')
    op.drop_table('support_escalations', schema='operations')
    op.drop_index(op.f('ix_system_settings_key'), table_name='system_settings', schema='operations')
    op.drop_table('system_settings', schema='operations')
