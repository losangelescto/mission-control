"""obstacles table

Revision ID: 0014_obstacles
Revises: 0013_sub_tasks
Create Date: 2026-04-22
"""
from alembic import op
import sqlalchemy as sa


revision = "0014_obstacles"
down_revision = "0013_sub_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "obstacles",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True, nullable=False),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("impact", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="active"),
        sa.Column("proposed_solutions", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("resolution_notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("identified_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("identified_by", sa.String(length=255), nullable=False, server_default="system"),
    )
    op.create_index("ix_obstacles_task_id", "obstacles", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_obstacles_task_id", table_name="obstacles")
    op.drop_table("obstacles")
