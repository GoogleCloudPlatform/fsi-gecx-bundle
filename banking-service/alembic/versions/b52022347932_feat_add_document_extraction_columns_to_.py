"""feat add document extraction columns to application_artifacts

Revision ID: b52022347932
Revises: 499636fd78cd
Create Date: 2026-06-28 21:58:00.676026

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b52022347932'
down_revision: Union[str, Sequence[str], None] = '499636fd78cd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to add OCR extraction columns to application_artifacts."""
    schema_name = 'ledger' if op.get_bind().dialect.name == 'sqlite' else 'origination'
    op.add_column('application_artifacts', sa.Column('actual_artifact_type', sa.String(length=100), nullable=True), schema=schema_name)
    op.add_column('application_artifacts', sa.Column('classification_confidence', sa.Float(), nullable=True), schema=schema_name)
    op.add_column('application_artifacts', sa.Column('extraction_payload', sa.Text(), nullable=True), schema=schema_name)
    op.add_column('application_artifacts', sa.Column('audit_metadata', sa.Text(), nullable=True), schema=schema_name)
    op.add_column('application_artifacts', sa.Column('verification_tier', sa.String(length=50), nullable=True), schema=schema_name)


def downgrade() -> None:
    """Downgrade schema."""
    schema_name = 'ledger' if op.get_bind().dialect.name == 'sqlite' else 'origination'
    op.drop_column('application_artifacts', 'verification_tier', schema=schema_name)
    op.drop_column('application_artifacts', 'audit_metadata', schema=schema_name)
    op.drop_column('application_artifacts', 'extraction_payload', schema=schema_name)
    op.drop_column('application_artifacts', 'classification_confidence', schema=schema_name)
    op.drop_column('application_artifacts', 'actual_artifact_type', schema=schema_name)
