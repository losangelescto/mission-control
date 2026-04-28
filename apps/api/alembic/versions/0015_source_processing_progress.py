"""add processing progress + metadata columns to source_documents

Revision ID: 0015_source_processing_progress
Revises: 0014_obstacles
Create Date: 2026-04-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_source_processing_progress"
down_revision = "0014_obstacles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_documents",
        sa.Column("pages_processed", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "source_documents",
        sa.Column("pages_total", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "source_documents",
        sa.Column("processing_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "source_documents",
        sa.Column("processing_metadata", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("source_documents", "processing_metadata")
    op.drop_column("source_documents", "processing_error")
    op.drop_column("source_documents", "pages_total")
    op.drop_column("source_documents", "pages_processed")
