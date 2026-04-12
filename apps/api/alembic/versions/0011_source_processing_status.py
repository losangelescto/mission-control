"""add processing_status to source_documents

Revision ID: 0011_source_processing_status
Revises: 0010_standard_scores
Create Date: 2026-04-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_source_processing_status"
down_revision = "0010_standard_scores"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_documents",
        sa.Column("processing_status", sa.String(50), nullable=False, server_default="complete"),
    )


def downgrade() -> None:
    op.drop_column("source_documents", "processing_status")
