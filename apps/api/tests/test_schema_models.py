from app.db import Base
from app import models  # noqa: F401


def test_expected_tables_exist() -> None:
    expected = {
        "tasks",
        "task_updates",
        "blockers",
        "delegations",
        "recurrence_templates",
        "recurrence_occurrences",
        "source_documents",
        "source_chunks",
        "task_candidates",
        "recommendations",
        "audit_events",
        "mailbox_sources",
        "mailbox_threads",
        "mailbox_messages",
        "mailbox_sync_state",
        "call_artifacts",
        "daily_rollups",
    }
    assert expected.issubset(set(Base.metadata.tables.keys()))


def test_tasks_required_columns_exist() -> None:
    tasks = Base.metadata.tables["tasks"]
    required_columns = {
        "title",
        "description",
        "objective",
        "standard",
        "status",
        "priority",
        "owner_name",
        "assigner_name",
        "due_at",
        "source_confidence",
        "created_at",
        "updated_at",
    }
    assert required_columns.issubset(set(tasks.columns.keys()))


def test_source_chunks_has_vector_embedding_column() -> None:
    source_chunks = Base.metadata.tables["source_chunks"]
    assert "embedding" in source_chunks.columns
    assert source_chunks.columns["embedding"].type.__class__.__name__ == "VECTOR"
