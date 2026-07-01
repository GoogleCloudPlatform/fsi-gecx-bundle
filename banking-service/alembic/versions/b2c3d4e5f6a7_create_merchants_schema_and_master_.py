"""create merchants schema and 3NF normalized master/stores tables for merchant intelligence

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
    # 0. Ensure merchants schema exists in PostgreSQL
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE SCHEMA IF NOT EXISTS merchants;")

    # 1. Ensure merchant_category_codes lookup table exists in ref_data schema
    op.create_table(
        'merchant_category_codes',
        sa.Column('mcc', sa.String(length=10), nullable=False),
        sa.Column('primary_category', sa.String(length=50), nullable=False),
        sa.Column('detailed_category', sa.String(length=100), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('mcc'),
        schema='ref_data'
    )

    # 2. Create normalized merchant_master table in merchants schema
    op.create_table(
        'merchant_master',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('merchant_id', sa.String(length=100), nullable=False),
        sa.Column('clean_name', sa.String(length=100), nullable=False),
        sa.Column('default_mcc', sa.String(length=10), nullable=False),
        sa.Column('merchant_domain', sa.String(length=100), nullable=True),
        sa.Column('logo_url', sa.String(length=255), nullable=True),
        sa.Column('is_subscription', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('merchant_id'),
        schema='merchants'
    )

    # 3. Create normalized merchant_stores table in merchants schema
    op.create_table(
        'merchant_stores',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('merchant_id', sa.String(length=100), sa.ForeignKey('merchants.merchant_master.merchant_id', ondelete='CASCADE'), nullable=False),
        sa.Column('location_name', sa.String(length=100), nullable=False),
        sa.Column('raw_descriptor', sa.String(length=150), nullable=False),
        sa.Column('country_code', sa.String(length=3), nullable=False, server_default='USA'),
        sa.Column('is_international', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('risk_score', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        schema='merchants'
    )

    # 4. Create performance indexes
    op.create_index('idx_merchants_mcc', 'merchant_master', ['default_mcc'], unique=False, schema='merchants')
    op.create_index('idx_merchants_domain', 'merchant_master', ['merchant_domain'], unique=False, schema='merchants')
    op.create_index('idx_stores_descriptor', 'merchant_stores', ['raw_descriptor'], unique=False, schema='merchants')
    op.create_index('idx_stores_country', 'merchant_stores', ['country_code', 'is_international'], unique=False, schema='merchants')
    op.create_index('idx_stores_risk', 'merchant_stores', ['risk_score'], unique=False, schema='merchants')

    # 5. Grant permissions on merchants and ref_data schemas to IAM service accounts and DBA users
    if op.get_bind().dialect.name == "postgresql" and os.getenv("SKIP_IAM_GRANTS") != "true":
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
            for schema_name in ["ref_data", "merchants"]:
                try:
                    op.execute(f'DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = \'{role}\') THEN CREATE ROLE "{role}" NOLOGIN; END IF; END $$;')
                    op.execute(f'GRANT USAGE ON SCHEMA {schema_name} TO "{role}";')
                    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema_name} TO "{role}";')
                    op.execute(f'GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA {schema_name} TO "{role}";')
                    op.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {schema_name} GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{role}";')
                except Exception as e:
                    print(f"Notice: Could not grant {schema_name} permissions to {role}: {e}")


def downgrade() -> None:
    op.drop_index('idx_stores_risk', table_name='merchant_stores', schema='merchants')
    op.drop_index('idx_stores_country', table_name='merchant_stores', schema='merchants')
    op.drop_index('idx_stores_descriptor', table_name='merchant_stores', schema='merchants')
    op.drop_index('idx_merchants_domain', table_name='merchant_master', schema='merchants')
    op.drop_index('idx_merchants_mcc', table_name='merchant_master', schema='merchants')
    op.drop_table('merchant_stores', schema='merchants')
    op.drop_table('merchant_master', schema='merchants')
    op.drop_table('merchant_category_codes', schema='ref_data')
