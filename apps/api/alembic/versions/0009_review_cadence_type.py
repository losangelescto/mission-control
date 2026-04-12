"""add cadence_type to review_sessions

Revision ID: 0009_review_cadence_type
Revises: 0008_review_sessions
Create Date: 2026-04-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_review_cadence_type"
down_revision = "0008_review_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "review_sessions",
        sa.Column("cadence_type", sa.String(50), nullable=False, server_default="ad_hoc"),
    )


def downgrade() -> None:
    op.drop_column("review_sessions", "cadence_type")
