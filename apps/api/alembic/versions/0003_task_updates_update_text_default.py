"""task updates legacy update_text default

Revision ID: 0003_task_updates_text_default
Revises: 0002_task_updates_fields
Create Date: 2026-03-26 00:00:00.000002
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_task_updates_text_default"
down_revision: Union[str, Sequence[str], None] = "0002_task_updates_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "task_updates",
        "update_text",
        existing_type=sa.Text(),
        server_default=sa.text("''"),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "task_updates",
        "update_text",
        existing_type=sa.Text(),
        server_default=None,
        existing_nullable=False,
    )
