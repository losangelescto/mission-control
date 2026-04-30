"""extend audit_events with action/actor/changes/metadata + indexes

Revision ID: 0018_audit_trail
Revises: 0017_search_vectors
Create Date: 2026-04-30

The existing ``audit_events`` table (event_type + payload_json) stays in
place for back-compat. We add four columns that the spec calls for:
``action`` (denormalised from event_type for the new code path),
``actor`` (who triggered the event), ``changes`` (the field-level diff),
and ``metadata`` (free-form context). Three indexes cover the three
documented query patterns: per-entity history, action-scan, and
actor-scan.
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_audit_trail"
down_revision = "0017_search_vectors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_events", sa.Column("action", sa.String(100), nullable=True))
    op.add_column(
        "audit_events",
        sa.Column("actor", sa.String(255), nullable=False, server_default="system"),
    )
    op.add_column("audit_events", sa.Column("changes", sa.JSON(), nullable=True))
    op.add_column("audit_events", sa.Column("event_metadata", sa.JSON(), nullable=True))

    # Backfill action from the legacy event_type column for existing rows.
    op.execute("UPDATE audit_events SET action = event_type WHERE action IS NULL")
    op.alter_column("audit_events", "action", nullable=False)

    op.create_index(
        "ix_audit_events_entity",
        "audit_events",
        ["entity_type", "entity_id", "created_at"],
    )
    op.create_index(
        "ix_audit_events_action",
        "audit_events",
        ["action", "created_at"],
    )
    op.create_index(
        "ix_audit_events_actor",
        "audit_events",
        ["actor", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_actor", table_name="audit_events")
    op.drop_index("ix_audit_events_action", table_name="audit_events")
    op.drop_index("ix_audit_events_entity", table_name="audit_events")
    op.drop_column("audit_events", "event_metadata")
    op.drop_column("audit_events", "changes")
    op.drop_column("audit_events", "actor")
    op.drop_column("audit_events", "action")
