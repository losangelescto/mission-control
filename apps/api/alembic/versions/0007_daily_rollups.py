"""daily rollups (phase 1 preview artifacts)

Revision ID: 0007_daily_rollups
Revises: 0006_call_artifacts
Create Date: 2026-03-27 00:00:00.000004
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_daily_rollups"
down_revision: Union[str, Sequence[str], None] = "0006_call_artifacts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "daily_rollups",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("preview_text", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_daily_rollups_generated_at", "daily_rollups", ["generated_at"])


def downgrade() -> None:
    op.drop_index("ix_daily_rollups_generated_at", table_name="daily_rollups")
    op.drop_table("daily_rollups")
