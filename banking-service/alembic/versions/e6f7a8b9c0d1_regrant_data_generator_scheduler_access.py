"""regrant data generator scheduler access

Revision ID: e6f7a8b9c0d1
Revises: d4e5f6a7b8c9
Create Date: 2026-07-11 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import os
import re


revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _project_id() -> str | None:
    for env_name in ("PROJECT_ID", "GOOGLE_CLOUD_PROJECT", "GCP_PROJECT", "GCLOUD_PROJECT"):
        value = os.getenv(env_name)
        if value:
            return value

    database_url = os.getenv("DATABASE_URL", "")
    match = re.search(r"/cloudsql/([^:/?]+):", database_url)
    if match:
        return match.group(1)

    try:
        from utils.gcp import get_project_id

        value = get_project_id()
        if str(value) != "None":
            return value
    except Exception:
        pass
    return None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql" or os.getenv("SKIP_IAM_GRANTS") == "true":
        return
    project_id = _project_id()
    if not project_id:
        raise RuntimeError("Unable to resolve project id for Data Generator scheduler grants.")

    user = f"datagen-service-sa@{project_id}.iam"
    op.execute(
        f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{user}') "
        f'THEN CREATE ROLE "{user}" NOLOGIN; END IF; END $$;'
    )
    op.execute(f'GRANT USAGE ON SCHEMA operations TO "{user}";')
    op.execute(
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE operations.synthetic_scheduled_events TO "{user}";'
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql" or os.getenv("SKIP_IAM_GRANTS") == "true":
        return
    project_id = _project_id()
    if not project_id:
        return
    user = f"datagen-service-sa@{project_id}.iam"
    op.execute(
        f'REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE operations.synthetic_scheduled_events FROM "{user}";'
    )
