"""create identity.user_addresses 3nf table

Revision ID: ecb21ff20cef
Revises: b2c3d4e5f6a7
Create Date: 2026-07-02 15:00:49.390862

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import utils.database

# revision identifiers, used by Alembic.
revision: str = 'ecb21ff20cef'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('user_addresses',
        sa.Column('id', utils.database.UniversalUUID(), nullable=False),
        sa.Column('user_id', utils.database.UniversalUUID(), nullable=False),
        sa.Column('address_type', sa.String(length=50), nullable=False),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('street_line_1', sa.String(length=255), nullable=False),
        sa.Column('street_line_2', sa.String(length=255), nullable=True),
        sa.Column('city', sa.String(length=100), nullable=False),
        sa.Column('state', sa.String(length=50), nullable=False),
        sa.Column('postal_code', sa.String(length=20), nullable=False),
        sa.Column('country_code', sa.String(length=3), nullable=False, server_default=sa.text("'USA'::character varying")),
        sa.Column('verified_by_doc_ai', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['identity.users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema='identity'
    )
    op.create_index('idx_user_addresses_user_id', 'user_addresses', ['user_id'], unique=False, schema='identity')
    op.create_index(op.f('ix_identity_user_addresses_city'), 'user_addresses', ['city'], unique=False, schema='identity')

    # Grant permissions to IAM service accounts and DBA users
    bind = op.get_bind()
    if bind.engine.name == "postgresql":
        for role in ["kyc-service-sa", "ledger-service-sa", "erikvoit@gcp.solutions"]:
            try:
                op.execute(f'DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = \'{role}\') THEN CREATE ROLE "{role}" NOLOGIN; END IF; END $$;')
                op.execute(f'GRANT USAGE ON SCHEMA identity TO "{role}";')
                op.execute(f'GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA identity TO "{role}";')
                op.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA identity GRANT ALL PRIVILEGES ON TABLES TO "{role}";')
            except Exception as e:
                print(f"Notice: Could not grant permissions to {role}: {e}")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_identity_user_addresses_city'), table_name='user_addresses', schema='identity')
    op.drop_index('idx_user_addresses_user_id', table_name='user_addresses', schema='identity')
    op.drop_table('user_addresses', schema='identity')
