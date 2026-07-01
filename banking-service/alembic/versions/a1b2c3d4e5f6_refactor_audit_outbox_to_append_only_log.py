"""Refactor audit_outbox table into append-only event log for WAL CDC

Revision ID: a1b2c3d4e5f6
Revises: 90b69c563699
Create Date: 2026-07-01 00:08:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '90b69c563699'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop status mutation columns and old partial index on status
    try:
        op.drop_index('idx_audit_outbox_pending', table_name='audit_outbox', schema='audit')
    except Exception:
        pass

    for col in ['status', 'retry_count', 'published_at']:
        try:
            op.drop_column('audit_outbox', col, schema='audit')
        except Exception:
            pass

    # 2. Add append-only event log indexes for CDC watermark and type filtering
    try:
        op.create_index('idx_audit_outbox_created_at', 'audit_outbox', ['created_at'], unique=False, schema='audit')
        op.create_index('idx_audit_outbox_event_type', 'audit_outbox', ['event_type'], unique=False, schema='audit')
    except Exception:
        pass


def downgrade() -> None:
    try:
        op.drop_index('idx_audit_outbox_event_type', table_name='audit_outbox', schema='audit')
        op.drop_index('idx_audit_outbox_created_at', table_name='audit_outbox', schema='audit')
    except Exception:
        pass

    op.add_column('audit_outbox', sa.Column('status', sa.String(length=20), nullable=False, server_default='PENDING'), schema='audit')
    op.add_column('audit_outbox', sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'), schema='audit')
    op.add_column('audit_outbox', sa.Column('published_at', sa.DateTime(), nullable=True), schema='audit')

    try:
        op.create_index('idx_audit_outbox_pending', 'audit_outbox', ['status'], unique=False, schema='audit', postgresql_where=sa.text("status = 'PENDING'"))
    except Exception:
        pass
