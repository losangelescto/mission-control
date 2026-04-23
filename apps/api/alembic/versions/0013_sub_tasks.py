"""sub_tasks table

Revision ID: 0013_sub_tasks
Revises: 0012_recommendation_history
Create Date: 2026-04-22
"""
from alembic import op
import sqlalchemy as sa


revision = "0013_sub_tasks"
down_revision = "0012_recommendation_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sub_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True, nullable=False),
        sa.Column("parent_task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("canon_reference", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sub_tasks_parent_task_id", "sub_tasks", ["parent_task_id"])


def downgrade() -> None:
    op.drop_index("ix_sub_tasks_parent_task_id", table_name="sub_tasks")
    op.drop_table("sub_tasks")
