"""add synthetic scheduled events

Revision ID: f2a4b6c8d9e1
Revises: c7e8d9a1b2f3
Create Date: 2026-07-11 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import utils.database


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
