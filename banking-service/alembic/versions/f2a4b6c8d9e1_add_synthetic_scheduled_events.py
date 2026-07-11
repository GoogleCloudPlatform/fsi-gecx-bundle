"""add synthetic scheduled events

Revision ID: f2a4b6c8d9e1
Revises: c7e8d9a1b2f3
Create Date: 2026-07-11 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import utils.database
import os


revision: str = "f2a4b6c8d9e1"
down_revision: Union[str, Sequence[str], None] = "c7e8d9a1b2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "synthetic_scheduled_events",
        sa.Column("id", utils.database.UniversalUUID(), nullable=False),
        sa.Column("schedule_id", sa.String(length=128), nullable=False),
        sa.Column("scenario_id", sa.String(length=128), nullable=True),
        sa.Column("execution_id", sa.String(length=128), nullable=True),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("parent_event_id", sa.String(length=128), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("persona_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result_payload", sa.JSON(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=1024), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("canceled_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_synthetic_scheduled_events_idempotency"
        ),
        schema="operations",
    )
    op.create_index(
        "idx_synthetic_scheduled_events_scenario",
        "synthetic_scheduled_events",
        ["scenario_id", "execution_id"],
        schema="operations",
    )
    op.create_index(
        "idx_synthetic_scheduled_events_schedule",
        "synthetic_scheduled_events",
        ["schedule_id", "scheduled_for"],
        schema="operations",
    )
    op.create_index(
        "idx_synthetic_scheduled_events_status_time",
        "synthetic_scheduled_events",
        ["status", "scheduled_for"],
        schema="operations",
    )

    if op.get_bind().dialect.name == "postgresql" and os.getenv("SKIP_IAM_GRANTS") != "true":
        try:
            from utils.gcp import get_project_id

            project_id = get_project_id()
            if str(project_id) == "None":
                project_id = os.getenv("PROJECT_ID")
        except Exception:
            project_id = os.getenv("PROJECT_ID")

        if project_id and str(project_id) != "None":
            user = f"data-generator-sa@{project_id}.iam"
            try:
                op.execute(f'DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = \'{user}\') THEN CREATE ROLE "{user}" NOLOGIN; END IF; END $$;')
                op.execute(f'GRANT USAGE ON SCHEMA operations TO "{user}";')
                op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE operations.synthetic_scheduled_events TO "{user}";')
            except Exception:
                pass


def downgrade() -> None:
    op.drop_index(
        "idx_synthetic_scheduled_events_status_time",
        table_name="synthetic_scheduled_events",
        schema="operations",
    )
    op.drop_index(
        "idx_synthetic_scheduled_events_schedule",
        table_name="synthetic_scheduled_events",
        schema="operations",
    )
    op.drop_index(
        "idx_synthetic_scheduled_events_scenario",
        table_name="synthetic_scheduled_events",
        schema="operations",
    )
    op.drop_table("synthetic_scheduled_events", schema="operations")
