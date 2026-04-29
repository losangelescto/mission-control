"""add search_vector tsvector columns + GIN indexes for unified search

Revision ID: 0017_search_vectors
Revises: 0016_canon_changes
Create Date: 2026-04-29

Postgres-only. The columns are STORED GENERATED, so the engine keeps the
tsvector in sync on every INSERT/UPDATE and we don't need triggers or
backfill — existing rows pick up the value the next time they're written,
and a one-shot ``UPDATE table SET id = id`` would force a rewrite if the
backfill ever needs to be eager. We deliberately skip that here because
generated columns compute lazily on read for unmodified rows would lose
the index benefit; PG actually computes them on the upgrade and the
``ALTER TABLE ... ADD COLUMN ... GENERATED`` DDL fills every row.
"""
from alembic import op

revision = "0017_search_vectors"
down_revision = "0016_canon_changes"
branch_labels = None
depends_on = None


_TSVECTOR_EXPRS: dict[str, str] = {
    "tasks": (
        "setweight(to_tsvector('english', coalesce(title,'')), 'A') || "
        "setweight(to_tsvector('english', coalesce(description,'')), 'B') || "
        "setweight(to_tsvector('english', coalesce(objective,'')), 'B') || "
        "setweight(to_tsvector('english', coalesce(standard,'')), 'C')"
    ),
    "task_updates": (
        "setweight(to_tsvector('english', coalesce(summary,'')), 'A') || "
        "setweight(to_tsvector('english', coalesce(what_happened,'')), 'B') || "
        "setweight(to_tsvector('english', coalesce(next_step,'')), 'B') || "
        "setweight(to_tsvector('english', coalesce(options_considered,'')), 'C') || "
        "setweight(to_tsvector('english', coalesce(steps_taken,'')), 'C')"
    ),
    "source_documents": (
        # Keep this small — the per-chunk index covers the body. We only
        # boost discoverability of the document itself by name + canon ids.
        "setweight(to_tsvector('english', coalesce(filename,'')), 'A') || "
        "setweight(to_tsvector('english', coalesce(canonical_doc_id,'')), 'B') || "
        "setweight(to_tsvector('english', coalesce(version_label,'')), 'C')"
    ),
    "source_chunks": "to_tsvector('english', coalesce(chunk_text,''))",
    "review_sessions": (
        "setweight(to_tsvector('english', coalesce(notes,'')), 'A') || "
        "setweight(to_tsvector('english', coalesce(action_items,'')), 'B') || "
        "setweight(to_tsvector('english', coalesce(reviewer,'')), 'C')"
    ),
    "sub_tasks": (
        "setweight(to_tsvector('english', coalesce(title,'')), 'A') || "
        "setweight(to_tsvector('english', coalesce(description,'')), 'B') || "
        "setweight(to_tsvector('english', coalesce(canon_reference,'')), 'C')"
    ),
    "obstacles": (
        "setweight(to_tsvector('english', coalesce(description,'')), 'A') || "
        "setweight(to_tsvector('english', coalesce(impact,'')), 'B') || "
        "setweight(to_tsvector('english', coalesce(resolution_notes,'')), 'C')"
    ),
}


def upgrade() -> None:
    for table, expression in _TSVECTOR_EXPRS.items():
        op.execute(
            f"ALTER TABLE {table} "
            f"ADD COLUMN search_vector tsvector "
            f"GENERATED ALWAYS AS ({expression}) STORED"
        )
        op.execute(
            f"CREATE INDEX ix_{table}_search_vector "
            f"ON {table} USING GIN (search_vector)"
        )


def downgrade() -> None:
    for table in reversed(list(_TSVECTOR_EXPRS.keys())):
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_search_vector")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS search_vector")
