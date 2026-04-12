"""call artifacts and task_candidate linkage

Revision ID: 0006_call_artifacts
Revises: 0005_mail_candidates
Create Date: 2026-03-27 00:00:00.000003
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_call_artifacts"
down_revision: Union[str, Sequence[str], None] = "0005_mail_candidates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "call_artifacts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("artifact_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("source_document_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_document_id"),
    )
    op.create_index("ix_call_artifacts_source_document_id", "call_artifacts", ["source_document_id"])

    op.add_column("task_candidates", sa.Column("call_artifact_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_task_candidates_call_artifact",
        "task_candidates",
        "call_artifacts",
        ["call_artifact_id"],
        ["id"],
    )
    op.create_index("ix_task_candidates_call_artifact_id", "task_candidates", ["call_artifact_id"])


def downgrade() -> None:
    op.drop_index("ix_task_candidates_call_artifact_id", table_name="task_candidates")
    op.drop_constraint("fk_task_candidates_call_artifact", "task_candidates", type_="foreignkey")
    op.drop_column("task_candidates", "call_artifact_id")
    op.drop_table("call_artifacts")
