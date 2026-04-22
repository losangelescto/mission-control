"""recommendation history fields

Revision ID: 0012_recommendation_history
Revises: 0011_source_processing_status
Create Date: 2026-04-20
"""
from alembic import op
import sqlalchemy as sa


revision = "0012_recommendation_history"
down_revision = "0011_source_processing_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recommendations",
        sa.Column(
            "recommendation_type",
            sa.String(length=50),
            nullable=False,
            server_default="standard",
        ),
    )
    op.add_column(
        "recommendations",
        sa.Column("input_context_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "recommendations",
        sa.Column("response_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("recommendations", "response_json")
    op.drop_column("recommendations", "input_context_hash")
    op.drop_column("recommendations", "recommendation_type")
