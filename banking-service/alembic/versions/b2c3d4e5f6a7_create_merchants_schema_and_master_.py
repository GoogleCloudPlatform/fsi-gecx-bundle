"""create merchants schema and master table for merchant intelligence

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-01 10:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import os


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create merchant_master table in ref_data schema
    op.create_table(
        'merchant_master',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('merchant_id', sa.String(length=100), nullable=False),
        sa.Column('clean_name', sa.String(length=100), nullable=False),
        sa.Column('raw_descriptor_pattern', sa.String(length=150), nullable=False),
        sa.Column('mcc', sa.String(length=10), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('country_code', sa.String(length=3), nullable=False, server_default='USA'),
        sa.Column('logo_url', sa.String(length=255), nullable=True),
        sa.Column('merchant_domain', sa.String(length=100), nullable=True),
        sa.Column('is_subscription', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_international', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('risk_score', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('merchant_id'),
        schema='ref_data'
    )

    # 2. Create performance indexes
    op.create_index('idx_merchants_mcc_country', 'merchant_master', ['mcc', 'country_code'], unique=False, schema='ref_data')
    op.create_index('idx_merchants_category', 'merchant_master', ['category'], unique=False, schema='ref_data')
    op.create_index('idx_merchants_international', 'merchant_master', ['is_international', 'risk_score'], unique=False, schema='ref_data')
    op.create_index('idx_merchants_domain', 'merchant_master', ['merchant_domain'], unique=False, schema='ref_data')

    # 3. Grant permissions on ref_data schema to IAM service accounts and DBA users
    if op.get_bind().dialect.name == "postgresql" and os.getenv("SKIP_IAM_GRANTS") != "true":
        import os
        from utils.gcp import get_project_id
        try:
            project_id = get_project_id()
            if str(project_id) == "None":
                project_id = os.getenv("PROJECT_ID")
        except Exception:
            project_id = os.getenv("PROJECT_ID")

        sa_names = ["banking-service-sa", "kyc-service-sa", "ledger-service-sa", "banking-db-migration-sa"]
        roles = [f"{sa}@{project_id}.iam" if project_id and str(project_id) != "None" else sa for sa in sa_names]
        if os.getenv("IAM_DBA_USERS"):
            roles.extend([u.strip() for u in os.getenv("IAM_DBA_USERS").split(",") if u.strip()])
        roles.extend(["erikvoit@gcp.solutions", "erikvoit@google.com", "banking_bq_connector"])

        for role in set(roles):
            try:
                op.execute(f'DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = \'{role}\') THEN CREATE ROLE "{role}" NOLOGIN; END IF; END $$;')
                op.execute(f'GRANT USAGE ON SCHEMA ref_data TO "{role}";')
                op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA ref_data TO "{role}";')
                op.execute(f'GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA ref_data TO "{role}";')
                op.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA ref_data GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{role}";')
            except Exception as e:
                print(f"Notice: Could not grant ref_data permissions to {role}: {e}")


def downgrade() -> None:
    op.drop_index('idx_merchants_domain', table_name='merchant_master', schema='ref_data')
    op.drop_index('idx_merchants_international', table_name='merchant_master', schema='ref_data')
    op.drop_index('idx_merchants_category', table_name='merchant_master', schema='ref_data')
    op.drop_index('idx_merchants_mcc_country', table_name='merchant_master', schema='ref_data')
    op.drop_table('merchant_master', schema='ref_data')
