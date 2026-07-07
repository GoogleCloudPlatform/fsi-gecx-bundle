"""grant permissions on dedicated schemas to service accounts

Revision ID: a59a8fe24cfd
Revises: 888d74ebf127
Create Date: 2026-06-27 20:57:50.237869

"""
import os
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a59a8fe24cfd'
down_revision: Union[str, Sequence[str], None] = '888d74ebf127'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Upgrade schema."""
    if op.get_bind().dialect.name != "postgresql" or os.getenv("SKIP_IAM_GRANTS") == "true":
        return

    try:
        from utils.gcp import get_project_id
        project_id = get_project_id()
        if str(project_id) == "None":
            project_id = os.getenv("PROJECT_ID")
    except Exception:
        project_id = os.getenv("PROJECT_ID")

    schemas = ["identity", "kyc", "ledger", "cards", "operations", "ref_data", "merchants"]

    users_by_schema = {
        "identity": [],
        "kyc": [],
        "ledger": [],
        "cards": [],
        "operations": [],
        "ref_data": [],
        "merchants": []
    }

    if project_id and str(project_id) != "None":
        main_sa = f"banking-service-sa@{project_id}.iam"
        for s in schemas:
            users_by_schema[s].append(main_sa)
        users_by_schema["kyc"].append(f"kyc-service-sa@{project_id}.iam")
        users_by_schema["ledger"].append(f"ledger-service-sa@{project_id}.iam")
        users_by_schema["ref_data"].append(f"kyc-service-sa@{project_id}.iam")
        users_by_schema["ref_data"].append(f"ledger-service-sa@{project_id}.iam")
        users_by_schema["merchants"].append(f"kyc-service-sa@{project_id}.iam")
        users_by_schema["merchants"].append(f"ledger-service-sa@{project_id}.iam")

    iam_dba_users_env = os.getenv("IAM_DBA_USERS")
    if iam_dba_users_env:
        for user in [u.strip() for u in iam_dba_users_env.split(",") if u.strip()]:
            for s in schemas:
                users_by_schema[s].append(user)

    all_users = set(u for u_list in users_by_schema.values() for u in u_list)

    iam_viewer_users_env = os.getenv("IAM_DB_VIEWER_USERS")
    viewer_users_by_schema = {s: [] for s in schemas}
    if iam_viewer_users_env:
        for user in [u.strip() for u in iam_viewer_users_env.split(",") if u.strip()]:
            for s in schemas:
                viewer_users_by_schema[s].append(user)

    all_viewer_users = set(u for u_list in viewer_users_by_schema.values() for u in u_list)

    for user in all_users | all_viewer_users:
        try:
            op.execute(f'DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = \'{user}\') THEN CREATE ROLE "{user}" NOLOGIN; END IF; END $$;')
        except Exception as e:
            print(f"Notice: Could not bootstrap role {user}: {e}")

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

    for schema_name, users in viewer_users_by_schema.items():
        for user in users:
            try:
                op.execute(f'GRANT USAGE ON SCHEMA {schema_name} TO "{user}";')
                op.execute(f'GRANT SELECT ON ALL TABLES IN SCHEMA {schema_name} TO "{user}";')
                op.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {schema_name} GRANT SELECT ON TABLES TO "{user}";')
            except Exception as e:
                print(f"Notice: Could not grant viewer permissions on {schema_name} to {user}: {e}")


def downgrade() -> None:
    """Downgrade schema."""
    pass
