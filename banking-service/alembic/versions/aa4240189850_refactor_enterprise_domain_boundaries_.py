"""refactor enterprise domain boundaries for origination cards and operations

Revision ID: aa4240189850
Revises: 03f1e74cfe99
Create Date: 2026-06-28 20:25:08.591326

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aa4240189850'
down_revision: Union[str, Sequence[str], None] = '03f1e74cfe99'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to enforce enterprise bounded contexts."""
    if op.get_bind().dialect.name != "postgresql":
        return

    # 1. Create origination schema and grant least-privilege permissions
    op.execute("CREATE SCHEMA IF NOT EXISTS origination")
    op.execute("GRANT USAGE ON SCHEMA origination TO \"banking-service-sa\", \"kyc-service-sa\", \"ledger-service-sa\"")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA origination TO \"banking-service-sa\", \"kyc-service-sa\", \"ledger-service-sa\"")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA origination GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO \"banking-service-sa\", \"kyc-service-sa\", \"ledger-service-sa\"")

    # 2. Relocate origination workflow tables from ledger to origination
    for table in ["applications", "application_artifacts", "mortgage_applications", "credit_card_applications", "deposit_applications"]:
        op.execute(f"ALTER TABLE IF EXISTS ledger.{table} SET SCHEMA origination")

    # 3. Relocate retail_locations from identity to operations
    op.execute("ALTER TABLE IF EXISTS identity.retail_locations SET SCHEMA operations")

    # 4. Rename cards.account_ledger to cards.posted_transactions
    op.execute("ALTER TABLE IF EXISTS cards.account_ledger RENAME TO posted_transactions")


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE IF EXISTS cards.posted_transactions RENAME TO account_ledger")
    op.execute("ALTER TABLE IF EXISTS operations.retail_locations SET SCHEMA identity")
    for table in ["applications", "application_artifacts", "mortgage_applications", "credit_card_applications", "deposit_applications"]:
        op.execute(f"ALTER TABLE IF EXISTS origination.{table} SET SCHEMA ledger")
