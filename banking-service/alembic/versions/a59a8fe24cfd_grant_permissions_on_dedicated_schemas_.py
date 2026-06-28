"""grant permissions on dedicated schemas to service accounts

Revision ID: a59a8fe24cfd
Revises: 888d74ebf127
Create Date: 2026-06-27 20:57:50.237869

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a59a8fe24cfd'
down_revision: Union[str, Sequence[str], None] = '888d74ebf127'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


import os

def upgrade() -> None:
    """Upgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return

    try:
        from utils.gcp import get_project_id
        project_id = get_project_id()
    except Exception:
        project_id = os.getenv("PROJECT_ID")

    schemas = ["identity", "kyc", "ledger", "cards", "operations"]

    users_by_schema = {
        "identity": [],
        "kyc": [],
        "ledger": [],
        "cards": [],
        "operations": []
    }

    if project_id:
        main_sa = f"banking-service-sa@{project_id}.iam"
        for s in schemas:
            users_by_schema[s].append(main_sa)
        users_by_schema["kyc"].append(f"kyc-service-sa@{project_id}.iam")
        users_by_schema["ledger"].append(f"ledger-service-sa@{project_id}.iam")

    iam_dba_users_env = os.getenv("IAM_DBA_USERS")
    if iam_dba_users_env:
        for user in [u.strip() for u in iam_dba_users_env.split(",") if u.strip()]:
            for s in schemas:
                users_by_schema[s].append(user)

    for schema_name, users in users_by_schema.items():
        for user in users:
            try:
                op.execute(f'GRANT USAGE ON SCHEMA {schema_name} TO "{user}";')
                op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema_name} TO "{user}";')
                op.execute(f'GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA {schema_name} TO "{user}";')
                op.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {schema_name} GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{user}";')
                op.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {schema_name} GRANT ALL PRIVILEGES ON SEQUENCES TO "{user}";')
            except Exception as e:
                print(f"Notice: Could not grant permissions on {schema_name} to {user}: {e}")


def downgrade() -> None:
    """Downgrade schema."""
    pass
