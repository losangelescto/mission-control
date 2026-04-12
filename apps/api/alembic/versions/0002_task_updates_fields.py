"""task updates structured fields

Revision ID: 0002_task_updates_fields
Revises: 0001_initial_schema
Create Date: 2026-03-26 00:00:00.000001
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_task_updates_fields"
down_revision: Union[str, Sequence[str], None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("task_updates", sa.Column("update_type", sa.String(length=50), server_default="note", nullable=False))
    op.add_column("task_updates", sa.Column("summary", sa.Text(), server_default="", nullable=False))
    op.add_column("task_updates", sa.Column("what_happened", sa.Text(), server_default="", nullable=False))
    op.add_column("task_updates", sa.Column("options_considered", sa.Text(), server_default="", nullable=False))
    op.add_column("task_updates", sa.Column("steps_taken", sa.Text(), server_default="", nullable=False))
    op.add_column("task_updates", sa.Column("next_step", sa.Text(), server_default="", nullable=False))
    op.add_column("task_updates", sa.Column("created_by", sa.String(length=255), server_default="system", nullable=False))


def downgrade() -> None:
    op.drop_column("task_updates", "created_by")
    op.drop_column("task_updates", "next_step")
    op.drop_column("task_updates", "steps_taken")
    op.drop_column("task_updates", "options_considered")
    op.drop_column("task_updates", "what_happened")
    op.drop_column("task_updates", "summary")
    op.drop_column("task_updates", "update_type")
