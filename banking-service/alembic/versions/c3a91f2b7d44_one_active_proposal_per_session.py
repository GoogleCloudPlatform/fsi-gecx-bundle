# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Enforce one unresolved proposal per customer support session.

Revision ID: c3a91f2b7d44
Revises: 91d7b4a6c2ef
Create Date: 2026-08-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3a91f2b7d44"
down_revision: Union[str, Sequence[str], None] = "91d7b4a6c2ef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ACTIVE_PREDICATE = (
    "status IN ('PROPOSED', 'PRESENTED', 'CONFIRMED', 'COMMITTING')"
)


def upgrade() -> None:
    duplicate = op.get_bind().execute(
        sa.text(
            """
            SELECT customer_id, support_session_id
            FROM operations.action_proposals
            WHERE status IN ('PROPOSED', 'PRESENTED', 'CONFIRMED', 'COMMITTING')
            GROUP BY customer_id, support_session_id
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot enforce active proposal uniqueness while a customer support "
            "session has multiple unresolved proposals. Resolve them explicitly "
            "before retrying the migration."
        )

    op.create_index(
        "uq_action_proposals_active_session",
        "action_proposals",
        ["customer_id", "support_session_id"],
        unique=True,
        schema="operations",
        postgresql_where=sa.text(_ACTIVE_PREDICATE),
        sqlite_where=sa.text(_ACTIVE_PREDICATE),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_action_proposals_active_session",
        table_name="action_proposals",
        schema="operations",
    )
