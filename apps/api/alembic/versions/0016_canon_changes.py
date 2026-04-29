"""enhanced extraction fields, canon_change_events, tasks.canon_update_pending

Revision ID: 0016_canon_changes
Revises: 0015_source_processing_progress
Create Date: 2026-04-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0016_canon_changes"
down_revision = "0015_source_processing_progress"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Richer LLM-derived candidate fields. extraction_kind already lives in
    # task_candidates.hints_json so we don't promote it to a column here.
    op.add_column(
        "task_candidates",
        sa.Column("suggested_priority", sa.String(50), nullable=True),
    )
    op.add_column(
        "task_candidates",
        sa.Column("source_reference", sa.Text(), nullable=True),
    )
    op.add_column(
        "task_candidates",
        sa.Column("source_timestamp", sa.String(64), nullable=True),
    )
    op.add_column(
        "task_candidates",
        sa.Column("canon_alignment", sa.String(255), nullable=True),
    )

    # Per-task flag for canon-change notifications. Reset to false when an
    # affected task is reviewed/acknowledged.
    op.add_column(
        "tasks",
        sa.Column(
            "canon_update_pending",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.create_table(
        "canon_change_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("canon_doc_id", sa.String(255), nullable=False, index=True),
        sa.Column(
            "previous_source_id",
            sa.Integer(),
            sa.ForeignKey("source_documents.id"),
            nullable=True,
        ),
        sa.Column(
            "new_source_id",
            sa.Integer(),
            sa.ForeignKey("source_documents.id"),
            nullable=False,
        ),
        sa.Column("change_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("affected_task_ids", sa.JSON(), nullable=False),
        sa.Column("impact_analysis", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "reviewed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_canon_change_events_reviewed_created",
        "canon_change_events",
        ["reviewed", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_canon_change_events_reviewed_created", table_name="canon_change_events")
    op.drop_table("canon_change_events")
    op.drop_column("tasks", "canon_update_pending")
    op.drop_column("task_candidates", "canon_alignment")
    op.drop_column("task_candidates", "source_timestamp")
    op.drop_column("task_candidates", "source_reference")
    op.drop_column("task_candidates", "suggested_priority")
