"""realign application extension tables with surrogate PKs and domain isolated requested amounts

Revision ID: c1a2b3c4d5e6
Revises: b52022347932
Create Date: 2026-06-29 13:35:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'b52022347932'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    schema_name = 'ledger' if op.get_bind().dialect.name == 'sqlite' else 'origination'

    if op.get_bind().dialect.name != 'sqlite':
        # 1. Add requested_loan_cents to mortgage_applications
        op.add_column('mortgage_applications', sa.Column('requested_loan_cents', sa.BigInteger(), nullable=True), schema=schema_name)

        # 2. Migrate existing mortgage requested amounts from applications to mortgage_applications
        op.execute(f"""
            INSERT INTO {schema_name}.mortgage_applications (application_id, requested_loan_cents)
            SELECT id, requested_amount_cents FROM {schema_name}.applications
            WHERE product_category = 'MORTGAGE' AND requested_amount_cents IS NOT NULL
            ON CONFLICT (application_id) DO UPDATE SET requested_loan_cents = EXCLUDED.requested_loan_cents;
        """)

        # 3. Drop requested_amount_cents from applications
        op.drop_column('applications', 'requested_amount_cents', schema=schema_name)

        # 4. Add surrogate PKs and unique FK constraints to child extension tables
        for tbl in ['mortgage_applications', 'credit_card_applications', 'deposit_applications']:
            op.execute(f"ALTER TABLE {schema_name}.{tbl} DROP CONSTRAINT {tbl}_pkey;")
            op.add_column(tbl, sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False), schema=schema_name)
            op.create_primary_key(f"pk_{tbl}", tbl, ['id'], schema=schema_name)
            op.create_unique_constraint(f"uq_{tbl}_app_id", tbl, ['application_id'], schema=schema_name)


def downgrade() -> None:
    schema_name = 'ledger' if op.get_bind().dialect.name == 'sqlite' else 'origination'

    if op.get_bind().dialect.name != 'sqlite':
        for tbl in ['mortgage_applications', 'credit_card_applications', 'deposit_applications']:
            op.drop_constraint(f"uq_{tbl}_app_id", tbl, schema=schema_name, type_='unique')
            op.execute(f"ALTER TABLE {schema_name}.{tbl} DROP CONSTRAINT pk_{tbl};")
            op.drop_column(tbl, 'id', schema=schema_name)
            op.create_primary_key(f"{tbl}_pkey", tbl, ['application_id'], schema=schema_name)

        op.add_column('applications', sa.Column('requested_amount_cents', sa.BigInteger(), nullable=True), schema=schema_name)
        op.execute(f"""
            UPDATE {schema_name}.applications a
            SET requested_amount_cents = m.requested_loan_cents
            FROM {schema_name}.mortgage_applications m
            WHERE a.id = m.application_id;
        """)
        op.drop_column('mortgage_applications', 'requested_loan_cents', schema=schema_name)
