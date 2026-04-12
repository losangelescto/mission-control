"""review sessions table

Revision ID: 0008_review_sessions
Revises: 0007_daily_rollups
Create Date: 2026-04-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_review_sessions"
down_revision = "0007_daily_rollups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=True, index=True),
        sa.Column("owner_name", sa.String(255), nullable=True, index=True),
        sa.Column("reviewer", sa.String(255), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("action_items", sa.Text(), nullable=False, server_default=""),
        sa.Column("next_review_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("review_sessions")
