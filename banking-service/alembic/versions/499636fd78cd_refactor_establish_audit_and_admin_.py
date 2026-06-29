"""refactor establish audit and admin schemas and rename credit card account table

Revision ID: 499636fd78cd
Revises: aa4240189850
Create Date: 2026-06-28 21:09:58.371567

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '499636fd78cd'
down_revision: Union[str, Sequence[str], None] = 'aa4240189850'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to establish audit and admin bounded contexts and rename card account table."""
    if op.get_bind().dialect.name != "postgresql":
        return

    # 1. Create audit and admin schemas (permissions handled programmatically by env.py post-upgrade hook)
    op.execute("CREATE SCHEMA IF NOT EXISTS audit")
    op.execute("CREATE SCHEMA IF NOT EXISTS admin")

    # 2. Relocate audit_outbox from ledger to audit
    op.execute("ALTER TABLE IF EXISTS ledger.audit_outbox SET SCHEMA audit")

    # 3. Relocate system_settings from operations to admin
    op.execute("ALTER TABLE IF EXISTS operations.system_settings SET SCHEMA admin")

    # 4. Rename cards.financial_account to cards.credit_accounts
    op.execute("ALTER TABLE IF EXISTS cards.financial_account RENAME TO credit_accounts")


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE IF EXISTS cards.credit_accounts RENAME TO financial_account")
    op.execute("ALTER TABLE IF EXISTS admin.system_settings SET SCHEMA operations")
    op.execute("ALTER TABLE IF EXISTS audit.audit_outbox SET SCHEMA ledger")
