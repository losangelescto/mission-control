"""standard scores table for Seven Standards and Five Emotional Signatures

Revision ID: 0010_standard_scores
Revises: 0009_review_cadence_type
Create Date: 2026-04-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_standard_scores"
down_revision = "0009_review_cadence_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "standard_scores",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scope_type", sa.String(50), nullable=False, index=True),
        sa.Column("scope_id", sa.String(255), nullable=False, server_default="default"),
        sa.Column("metric_type", sa.String(50), nullable=False),  # "standard" or "signature"
        sa.Column("metric_name", sa.String(255), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("assessment", sa.Text(), nullable=False, server_default=""),
        sa.Column("period", sa.String(50), nullable=False, server_default="current"),
        sa.Column("updated_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("standard_scores")
