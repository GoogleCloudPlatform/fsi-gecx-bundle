"""grant data generator scheduler access

Revision ID: d4e5f6a7b8c9
Revises: f2a4b6c8d9e1
Create Date: 2026-07-11 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import os


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "f2a4b6c8d9e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _project_id() -> str | None:
    try:
        from utils.gcp import get_project_id

        value = get_project_id()
        if str(value) != "None":
            return value
    except Exception:
        pass
    return os.getenv("PROJECT_ID")


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql" or os.getenv("SKIP_IAM_GRANTS") == "true":
        return
    project_id = _project_id()
    if not project_id or str(project_id) == "None":
        return
    user = f"data-generator-sa@{project_id}.iam"
    try:
        op.execute(f'DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = \'{user}\') THEN CREATE ROLE "{user}" NOLOGIN; END IF; END $$;')
        op.execute(f'GRANT USAGE ON SCHEMA operations TO "{user}";')
        op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE operations.synthetic_scheduled_events TO "{user}";')
    except Exception:
        pass


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql" or os.getenv("SKIP_IAM_GRANTS") == "true":
        return
    project_id = _project_id()
    if not project_id or str(project_id) == "None":
        return
    user = f"data-generator-sa@{project_id}.iam"
    try:
        op.execute(f'REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE operations.synthetic_scheduled_events FROM "{user}";')
    except Exception:
        pass
