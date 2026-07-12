"""Add raw air-quality signals (PM2.5 + European AQI) captured per scoring run.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("history", sa.Column("pm2_5", sa.Float(), nullable=True))
    op.add_column("history", sa.Column("european_aqi", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("history", "european_aqi")
    op.drop_column("history", "pm2_5")
