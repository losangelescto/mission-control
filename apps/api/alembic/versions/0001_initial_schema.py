"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-03-26 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("standard", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("priority", sa.String(length=50), nullable=False),
        sa.Column("owner_name", sa.String(length=255), nullable=False),
        sa.Column("assigner_name", sa.String(length=255), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "task_updates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("update_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_task_updates_task_id", "task_updates", ["task_id"])

    op.create_table(
        "blockers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("blocker_type", sa.String(length=100), nullable=False),
        sa.Column("blocker_reason", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=50), nullable=False),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_blockers_task_id", "blockers", ["task_id"])

    op.create_table(
        "delegations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("delegated_from", sa.String(length=255), nullable=False),
        sa.Column("delegated_to", sa.String(length=255), nullable=False),
        sa.Column("delegated_by", sa.String(length=255), nullable=False),
        sa.Column("delegated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_delegations_task_id", "delegations", ["task_id"])

    op.create_table(
        "recurrence_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("cadence", sa.String(length=100), nullable=False),
        sa.Column("default_owner_name", sa.String(length=255), nullable=False),
        sa.Column("default_assigner_name", sa.String(length=255), nullable=False),
        sa.Column("default_due_window_days", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )

    op.create_table(
        "recurrence_occurrences",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("recurrence_template_id", sa.Integer(), sa.ForeignKey("recurrence_templates.id"), nullable=False),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("occurrence_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
    )
    op.create_index(
        "ix_recurrence_occurrences_recurrence_template_id",
        "recurrence_occurrences",
        ["recurrence_template_id"],
    )
    op.create_index("ix_recurrence_occurrences_task_id", "recurrence_occurrences", ["task_id"])

    op.create_table(
        "source_documents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=100), nullable=False),
        sa.Column("canonical_doc_id", sa.String(length=255), nullable=True),
        sa.Column("version_label", sa.String(length=255), nullable=True),
        sa.Column("is_active_canon_version", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "source_chunks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_document_id", sa.Integer(), sa.ForeignKey("source_documents.id"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_source_chunks_source_document_id", "source_chunks", ["source_document_id"])

    op.create_table(
        "task_candidates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_document_id", sa.Integer(), sa.ForeignKey("source_documents.id"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("inferred_owner_name", sa.String(length=255), nullable=True),
        sa.Column("inferred_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fallback_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_status", sa.String(length=50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_task_candidates_source_document_id", "task_candidates", ["source_document_id"])

    op.create_table(
        "recommendations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("standard", sa.Text(), nullable=False),
        sa.Column("first_principles_plan", sa.Text(), nullable=False),
        sa.Column("viable_options_json", sa.JSON(), nullable=False),
        sa.Column("next_action", sa.Text(), nullable=False),
        sa.Column("source_refs_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_recommendations_task_id", "recommendations", ["task_id"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_index("ix_recommendations_task_id", table_name="recommendations")
    op.drop_table("recommendations")
    op.drop_index("ix_task_candidates_source_document_id", table_name="task_candidates")
    op.drop_table("task_candidates")
    op.drop_index("ix_source_chunks_source_document_id", table_name="source_chunks")
    op.drop_table("source_chunks")
    op.drop_table("source_documents")
    op.drop_index("ix_recurrence_occurrences_task_id", table_name="recurrence_occurrences")
    op.drop_index(
        "ix_recurrence_occurrences_recurrence_template_id",
        table_name="recurrence_occurrences",
    )
    op.drop_table("recurrence_occurrences")
    op.drop_table("recurrence_templates")
    op.drop_index("ix_delegations_task_id", table_name="delegations")
    op.drop_table("delegations")
    op.drop_index("ix_blockers_task_id", table_name="blockers")
    op.drop_table("blockers")
    op.drop_index("ix_task_updates_task_id", table_name="task_updates")
    op.drop_table("task_updates")
    op.drop_table("tasks")
