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
    import os
    try:
        from utils.gcp import get_project_id
        project_id = get_project_id()
    except Exception:
        project_id = os.getenv("PROJECT_ID")

    sa_names = ["banking-service-sa", "kyc-service-sa", "ledger-service-sa"]
    roles = [f"{sa}@{project_id}.iam" if project_id else sa for sa in sa_names]
    
    for role in roles:
        try:
            op.execute(f'GRANT USAGE ON SCHEMA origination TO "{role}"')
            op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA origination TO "{role}"')
            op.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA origination GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{role}"')
        except Exception as e:
            print(f"Notice: Could not grant permissions on origination to {role}: {e}")

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
