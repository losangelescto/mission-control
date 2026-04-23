from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db import get_db
from app.main import app
from app.models import (
    AuditEvent,
    Blocker,
    Delegation,
    Obstacle,
    Recommendation,
    ReviewSession,
    SourceChunk,
    SourceDocument,
    SubTask,
    Task,
    TaskUpdate,
)


def test_embed_retrieve_and_recommendation_routes(tmp_path) -> None:  # type: ignore[no-untyped-def]
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    SourceDocument.__table__.create(bind=engine)
    SourceChunk.__table__.create(bind=engine)
    Task.__table__.create(bind=engine)
    TaskUpdate.__table__.create(bind=engine)
    Blocker.__table__.create(bind=engine)
    Delegation.__table__.create(bind=engine)
    ReviewSession.__table__.create(bind=engine)
    Recommendation.__table__.create(bind=engine)
    SubTask.__table__.create(bind=engine)
    Obstacle.__table__.create(bind=engine)
    AuditEvent.__table__.create(bind=engine)

    settings = get_settings()
    settings.sources_upload_dir = str(tmp_path / "uploads")

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    canon_upload = client.post(
        "/sources/upload",
        data={"source_type": "canon_doc"},
        files={"file": ("canon.txt", b"TODO: task align standard for resident communication weekly", "text/plain")},
    )
    assert canon_upload.status_code == 201
    canon_id = canon_upload.json()["source_document"]["id"]
    register = client.post(
        f"/canon/register/{canon_id}",
        json={"canonical_doc_id": "canon-comm", "version_label": "v1"},
    )
    assert register.status_code == 200
    activate = client.post(f"/canon/activate/{canon_id}")
    assert activate.status_code == 200

    note_upload = client.post(
        "/sources/upload",
        data={"source_type": "note"},
        files={"file": ("history.txt", b"task history: previous issue blocked by dependency", "text/plain")},
    )
    assert note_upload.status_code == 201
    note_id = note_upload.json()["source_document"]["id"]

    embed_canon = client.post(f"/sources/{canon_id}/embed")
    assert embed_canon.status_code == 200
    assert embed_canon.json()["embedded_chunk_count"] >= 1
    embed_note = client.post(f"/sources/{note_id}/embed")
    assert embed_note.status_code == 200
    assert embed_note.json()["embedded_chunk_count"] >= 1

    search_all = client.post(
        "/retrieve/search",
        json={"query": "resident communication standard", "active_canon_only": False},
    )
    assert search_all.status_code == 200
    assert len(search_all.json()["results"]) >= 1

    search_canon_only = client.post(
        "/retrieve/search",
        json={"query": "resident communication", "active_canon_only": True},
    )
    assert search_canon_only.status_code == 200
    canon_results = search_canon_only.json()["results"]
    assert len(canon_results) >= 1
    assert all(row["source_type"] == "canon_doc" for row in canon_results)
    assert all(row["is_active_canon_version"] is True for row in canon_results)

    search_filter = client.post(
        "/retrieve/search",
        json={"query": "dependency", "active_canon_only": False, "source_types": ["note"]},
    )
    assert search_filter.status_code == 200
    filtered = search_filter.json()["results"]
    assert len(filtered) >= 1
    assert all(row["source_type"] == "note" for row in filtered)

    task_create = client.post(
        "/tasks",
        json={
            "title": "Improve resident updates",
            "description": "Need a better routine for resident comms",
            "objective": "Increase clarity and consistency",
            "standard": "Follow canon communication guidance",
            "status": "backlog",
            "priority": "high",
            "owner_name": "Alex",
            "assigner_name": "Jordan",
            "due_at": None,
            "source_confidence": 0.8,
        },
    )
    assert task_create.status_code == 201
    task_id = task_create.json()["id"]

    recommendation = client.post(f"/tasks/{task_id}/recommendation")
    assert recommendation.status_code == 200
    payload = recommendation.json()
    assert payload["task_id"] == task_id
    assert payload["objective"] == "Increase clarity and consistency"
    assert payload["standard"] == "Follow canon communication guidance"
    assert payload["first_principles_plan"]
    assert len(payload["viable_options"]) >= 2
    assert payload["next_action"]
    assert len(payload["source_refs"]) >= 1

    with TestingSessionLocal() as db:
        rec = db.scalar(select(Recommendation).where(Recommendation.task_id == task_id))
        assert rec is not None
        assert len(rec.viable_options_json) >= 2
        assert len(rec.source_refs_json) >= 1

    app.dependency_overrides.clear()
