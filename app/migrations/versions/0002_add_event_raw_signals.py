"""Add raw event signals (count + next start) captured by the events collector.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("history", sa.Column("event_count", sa.Integer(), nullable=True))
    op.add_column(
        "history",
        sa.Column("next_event_starts_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("history", "next_event_starts_at")
    op.drop_column("history", "event_count")
