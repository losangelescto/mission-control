"""task candidates mail linkage and thread refresh cursor

Revision ID: 0005_mail_candidates
Revises: 0004_mailbox_tables
Create Date: 2026-03-27 00:00:00.000002
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_mail_candidates"
down_revision: Union[str, Sequence[str], None] = "0004_mailbox_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "task_candidates",
        sa.Column(
            "hints_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )
    op.add_column(
        "task_candidates",
        sa.Column("candidate_kind", sa.String(length=50), server_default="new_task", nullable=False),
    )
    op.add_column("task_candidates", sa.Column("mailbox_message_id", sa.Integer(), nullable=True))
    op.add_column("task_candidates", sa.Column("mailbox_thread_id", sa.Integer(), nullable=True))
    op.add_column("task_candidates", sa.Column("related_task_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_task_candidates_mailbox_message",
        "task_candidates",
        "mailbox_messages",
        ["mailbox_message_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_task_candidates_mailbox_thread",
        "task_candidates",
        "mailbox_threads",
        ["mailbox_thread_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_task_candidates_related_task",
        "task_candidates",
        "tasks",
        ["related_task_id"],
        ["id"],
    )
    op.create_index("ix_task_candidates_mailbox_message_id", "task_candidates", ["mailbox_message_id"])
    op.create_index("ix_task_candidates_mailbox_thread_id", "task_candidates", ["mailbox_thread_id"])
    op.create_index("ix_task_candidates_related_task_id", "task_candidates", ["related_task_id"])

    op.add_column(
        "mailbox_threads",
        sa.Column("last_refresh_up_to_message_id", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("mailbox_threads", "last_refresh_up_to_message_id")

    op.drop_index("ix_task_candidates_related_task_id", table_name="task_candidates")
    op.drop_index("ix_task_candidates_mailbox_thread_id", table_name="task_candidates")
    op.drop_index("ix_task_candidates_mailbox_message_id", table_name="task_candidates")
    op.drop_constraint("fk_task_candidates_related_task", "task_candidates", type_="foreignkey")
    op.drop_constraint("fk_task_candidates_mailbox_thread", "task_candidates", type_="foreignkey")
    op.drop_constraint("fk_task_candidates_mailbox_message", "task_candidates", type_="foreignkey")
    op.drop_column("task_candidates", "related_task_id")
    op.drop_column("task_candidates", "mailbox_thread_id")
    op.drop_column("task_candidates", "mailbox_message_id")
    op.drop_column("task_candidates", "candidate_kind")
    op.drop_column("task_candidates", "hints_json")
