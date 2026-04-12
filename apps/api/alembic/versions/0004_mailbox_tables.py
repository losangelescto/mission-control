"""mailbox tables phase 1

Revision ID: 0004_mailbox_tables
Revises: 0003_task_updates_text_default
Create Date: 2026-03-27 00:00:00.000001
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_mailbox_tables"
down_revision: Union[str, Sequence[str], None] = "0003_task_updates_text_default"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mailbox_sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("mailbox_owner", sa.String(length=255), nullable=False),
        sa.Column("folder_name", sa.String(length=255), server_default="Inbox", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "mailbox_owner", "folder_name", name="uq_mailbox_sources_scope"),
    )
    op.create_table(
        "mailbox_threads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("mailbox_source_id", sa.Integer(), nullable=False),
        sa.Column("external_thread_id", sa.String(length=512), nullable=False),
        sa.Column("subject", sa.String(length=1024), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["mailbox_source_id"], ["mailbox_sources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "mailbox_source_id",
            "external_thread_id",
            name="uq_mailbox_threads_source_external_thread",
        ),
    )
    op.create_index("ix_mailbox_threads_mailbox_source_id", "mailbox_threads", ["mailbox_source_id"])
    op.create_table(
        "mailbox_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("mailbox_source_id", sa.Integer(), nullable=False),
        sa.Column("mailbox_thread_id", sa.Integer(), nullable=False),
        sa.Column("external_message_id", sa.String(length=512), nullable=False),
        sa.Column("external_thread_id", sa.String(length=512), nullable=False),
        sa.Column("mailbox_owner", sa.String(length=255), nullable=False),
        sa.Column("folder_name", sa.String(length=255), nullable=False),
        sa.Column("sender", sa.String(length=512), nullable=False),
        sa.Column("recipients_json", sa.JSON(), nullable=False),
        sa.Column("subject", sa.String(length=1024), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_document_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["mailbox_source_id"], ["mailbox_sources.id"]),
        sa.ForeignKeyConstraint(["mailbox_thread_id"], ["mailbox_threads.id"]),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "mailbox_source_id",
            "external_message_id",
            name="uq_mailbox_messages_source_external_id",
        ),
    )
    op.create_index("ix_mailbox_messages_mailbox_source_id", "mailbox_messages", ["mailbox_source_id"])
    op.create_index("ix_mailbox_messages_mailbox_thread_id", "mailbox_messages", ["mailbox_thread_id"])
    op.create_index("ix_mailbox_messages_source_document_id", "mailbox_messages", ["source_document_id"])
    op.create_table(
        "mailbox_sync_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("mailbox_source_id", sa.Integer(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cursor_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="idle", nullable=False),
        sa.ForeignKeyConstraint(["mailbox_source_id"], ["mailbox_sources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mailbox_source_id"),
    )
    op.create_index("ix_mailbox_sync_state_mailbox_source_id", "mailbox_sync_state", ["mailbox_source_id"])


def downgrade() -> None:
    op.drop_table("mailbox_sync_state")
    op.drop_table("mailbox_messages")
    op.drop_table("mailbox_threads")
    op.drop_table("mailbox_sources")
