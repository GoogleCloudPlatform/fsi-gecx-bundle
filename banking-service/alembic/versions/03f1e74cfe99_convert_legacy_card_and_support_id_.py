"""convert legacy card and support id columns from varchar to uuid in postgres

Revision ID: 03f1e74cfe99
Revises: a59a8fe24cfd
Create Date: 2026-06-27 21:27:19.272761

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '03f1e74cfe99'
down_revision: Union[str, Sequence[str], None] = 'a59a8fe24cfd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return

    # Clear legacy tables first per user guidance so type casting cannot fail on non-UUID mock strings
    op.execute("TRUNCATE TABLE cards.account_ledger, cards.transaction_authorization, cards.issued_card, cards.financial_account, operations.support_escalations CASCADE;")

    # Drop foreign key constraints
    for constraint_name, table_name in [
        ('account_ledger_authorization_id_fkey', 'account_ledger'),
        ('account_ledger_account_id_fkey', 'account_ledger'),
        ('transaction_authorization_card_id_fkey', 'transaction_authorization'),
        ('transaction_authorization_account_id_fkey', 'transaction_authorization'),
        ('issued_card_account_id_fkey', 'issued_card')
    ]:
        try:
            op.drop_constraint(constraint_name, table_name, schema='cards', type_='foreignkey')
        except Exception as e:
            print(f"Notice dropping FK {constraint_name}: {e}")

    # Convert column types from VARCHAR/text to UUID
    op.execute('ALTER TABLE cards.financial_account ALTER COLUMN id TYPE UUID USING id::uuid;')
    op.execute('ALTER TABLE cards.issued_card ALTER COLUMN id TYPE UUID USING id::uuid;')
    op.execute('ALTER TABLE cards.issued_card ALTER COLUMN account_id TYPE UUID USING account_id::uuid;')
    op.execute('ALTER TABLE cards.transaction_authorization ALTER COLUMN id TYPE UUID USING id::uuid;')
    op.execute('ALTER TABLE cards.transaction_authorization ALTER COLUMN account_id TYPE UUID USING account_id::uuid;')
    op.execute('ALTER TABLE cards.transaction_authorization ALTER COLUMN card_id TYPE UUID USING card_id::uuid;')
    op.execute('ALTER TABLE cards.account_ledger ALTER COLUMN id TYPE UUID USING id::uuid;')
    op.execute('ALTER TABLE cards.account_ledger ALTER COLUMN account_id TYPE UUID USING account_id::uuid;')
    op.execute('ALTER TABLE cards.account_ledger ALTER COLUMN authorization_id TYPE UUID USING authorization_id::uuid;')
    op.execute('ALTER TABLE operations.support_escalations ALTER COLUMN id TYPE UUID USING id::uuid;')

    # Re-create foreign keys
    op.create_foreign_key('issued_card_account_id_fkey', 'issued_card', 'financial_account', ['account_id'], ['id'], source_schema='cards', referent_schema='cards', ondelete='RESTRICT')
    op.create_foreign_key('transaction_authorization_account_id_fkey', 'transaction_authorization', 'financial_account', ['account_id'], ['id'], source_schema='cards', referent_schema='cards', ondelete='RESTRICT')
    op.create_foreign_key('transaction_authorization_card_id_fkey', 'transaction_authorization', 'issued_card', ['card_id'], ['id'], source_schema='cards', referent_schema='cards', ondelete='RESTRICT')
    op.create_foreign_key('account_ledger_account_id_fkey', 'account_ledger', 'financial_account', ['account_id'], ['id'], source_schema='cards', referent_schema='cards', ondelete='RESTRICT')
    op.create_foreign_key('account_ledger_authorization_id_fkey', 'account_ledger', 'transaction_authorization', ['authorization_id'], ['id'], source_schema='cards', referent_schema='cards', ondelete='SET NULL')


def downgrade() -> None:
    """Downgrade schema."""
    pass
