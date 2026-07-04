"""Initial schema: places and history (including raw signal columns).

Revision ID: 0001
Revises:
Create Date: 2026-07-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "places",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("address", sa.String(length=300), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=False),
        sa.Column("country", sa.String(length=120), nullable=False),
        sa.Column("google_place_id", sa.String(length=200), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("rating_count", sa.Integer(), nullable=True),
        sa.Column("osm_id", sa.String(length=60), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_places_name", "places", ["name"])
    op.create_index("ix_places_category", "places", ["category"])
    op.create_index("ix_places_city", "places", ["city"])

    op.create_table(
        "history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "place_id",
            sa.Integer(),
            sa.ForeignKey("places.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("activity_score", sa.Integer(), nullable=False),
        sa.Column("traffic_score", sa.Float(), nullable=True),
        sa.Column("weather_score", sa.Float(), nullable=True),
        sa.Column("event_score", sa.Float(), nullable=True),
        sa.Column("social_score", sa.Float(), nullable=True),
        sa.Column("temperature_c", sa.Float(), nullable=True),
        sa.Column("precipitation_mm", sa.Float(), nullable=True),
        sa.Column("current_speed_kmh", sa.Float(), nullable=True),
        sa.Column("free_flow_speed_kmh", sa.Float(), nullable=True),
        sa.Column("place_rating", sa.Float(), nullable=True),
        sa.Column("place_rating_count", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_history_place_id", "history", ["place_id"])
    op.create_index("ix_history_created_at", "history", ["created_at"])


def downgrade() -> None:
    op.drop_table("history")
    op.drop_table("places")
