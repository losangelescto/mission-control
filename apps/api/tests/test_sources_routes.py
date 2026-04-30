from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import db as db_module
from app.config import get_settings
from app.db import get_db
from app.main import app
from app.models import SourceChunk, SourceDocument


def _set_up_test_db(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    SourceDocument.__table__.create(bind=engine)
    SourceChunk.__table__.create(bind=engine)

    settings = get_settings()
    settings.sources_upload_dir = str(tmp_path / "uploads")

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(db_module, "SessionLocal", TestingSessionLocal)
    return TestingSessionLocal


def test_sources_upload_and_read_routes(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    TestingSessionLocal = _set_up_test_db(tmp_path, monkeypatch)
    client = TestClient(app)

    upload_response = client.post(
        "/sources/upload",
        data={"source_type": "note"},
        files={"file": ("note.txt", b"first line\nsecond line", "text/plain")},
    )
    assert upload_response.status_code == 201
    payload = upload_response.json()
    assert payload["source_document"]["source_type"] == "note"
    assert payload["source_document"]["filename"] == "note.txt"

    source_id = payload["source_document"]["id"]
    # Background task has already run by the time TestClient returns.
    get_response = client.get(f"/sources/{source_id}")
    assert get_response.status_code == 200
    assert get_response.json()["processing_status"] == "complete"

    status_response = client.get(f"/sources/{source_id}/status")
    assert status_response.status_code == 200
    assert status_response.json()["processing_status"] == "complete"

    list_response = client.get("/sources")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    with TestingSessionLocal() as db:
        chunks = list(
            db.scalars(select(SourceChunk).where(SourceChunk.source_document_id == source_id)).all()
        )
        assert len(chunks) >= 1

    app.dependency_overrides.clear()


def test_sources_upload_rejects_unsupported_extension(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_up_test_db(tmp_path, monkeypatch)
    client = TestClient(app)

    upload_response = client.post(
        "/sources/upload",
        data={"source_type": "note"},
        files={"file": ("image.png", b"fake", "image/png")},
    )
    assert upload_response.status_code == 400
    assert "unsupported file type" in upload_response.json()["detail"]

    app.dependency_overrides.clear()


def _setup_full_source_db(tmp_path, monkeypatch):
    """Brings up every table the source-delete cascade needs."""
    from app.models import (
        AuditEvent, Blocker, CallArtifact, CanonChangeEvent, Delegation,
        MailboxMessage, MailboxSource, MailboxThread, Obstacle,
        Recommendation, ReviewSession, SubTask, Task, TaskCandidate,
        TaskUpdate,
    )

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionTesting = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    for model in (
        SourceDocument, SourceChunk, Task, TaskUpdate, TaskCandidate,
        CallArtifact, AuditEvent, Blocker, Delegation, ReviewSession,
        Recommendation, SubTask, Obstacle, CanonChangeEvent,
        MailboxSource, MailboxThread, MailboxMessage,
    ):
        model.__table__.create(bind=engine)

    settings = get_settings()
    settings.sources_upload_dir = str(tmp_path / "uploads")

    def override_get_db() -> Generator[Session, None, None]:
        db = SessionTesting()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(db_module, "SessionLocal", SessionTesting)
    return SessionTesting


def test_delete_source_cascades_chunks(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    SessionTesting = _setup_full_source_db(tmp_path, monkeypatch)
    client = TestClient(app)

    upload = client.post(
        "/sources/upload",
        data={"source_type": "note"},
        files={"file": ("delete-me.txt", b"hello world\nmore text\nthird line", "text/plain")},
    )
    source_id = upload.json()["source_document"]["id"]
    # BackgroundTask completes before TestClient returns; chunks are written.
    with SessionTesting() as db:
        chunks_before = db.scalars(
            select(SourceChunk).where(SourceChunk.source_document_id == source_id)
        ).all()
        assert len(list(chunks_before)) >= 1

    resp = client.delete(f"/sources/{source_id}")
    assert resp.status_code == 204
    assert client.get(f"/sources/{source_id}").status_code == 404

    with SessionTesting() as db:
        assert db.execute(
            select(SourceChunk).where(SourceChunk.source_document_id == source_id)
        ).first() is None

    app.dependency_overrides.clear()


def test_delete_active_canon_requires_force(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_full_source_db(tmp_path, monkeypatch)
    client = TestClient(app)

    upload = client.post(
        "/sources/upload",
        data={"source_type": "canon_doc", "canonical_doc_id": "canon-x", "version_label": "v1"},
        files={"file": ("canon.txt", b"first canon", "text/plain")},
    )
    source_id = upload.json()["source_document"]["id"]
    # Promote to active canon — register then activate.
    register = client.post(
        f"/canon/register/{source_id}",
        json={"canonical_doc_id": "canon-x", "version_label": "v1"},
    )
    assert register.status_code == 200
    activate = client.post(f"/canon/activate/{source_id}")
    assert activate.status_code == 200

    blocked = client.delete(f"/sources/{source_id}")
    assert blocked.status_code == 409
    assert "active canon" in blocked.json()["detail"].lower()

    forced = client.delete(f"/sources/{source_id}?force=true")
    assert forced.status_code == 204
    assert client.get(f"/sources/{source_id}").status_code == 404

    app.dependency_overrides.clear()


def test_delete_source_emits_audit(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_full_source_db(tmp_path, monkeypatch)
    client = TestClient(app)

    upload = client.post(
        "/sources/upload",
        data={"source_type": "note"},
        files={"file": ("audit.txt", b"audit me", "text/plain")},
    )
    source_id = upload.json()["source_document"]["id"]
    assert client.delete(f"/sources/{source_id}").status_code == 204

    audit = client.get(f"/audit?entity_type=source&entity_id={source_id}").json()
    actions = [e["action"] for e in audit["events"]]
    assert "deleted" in actions
    deleted_event = next(e for e in audit["events"] if e["action"] == "deleted")
    assert deleted_event["changes"]["source"]["filename"] == "audit.txt"

    app.dependency_overrides.clear()


def test_delete_source_not_found(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_full_source_db(tmp_path, monkeypatch)
    client = TestClient(app)

    resp = client.delete("/sources/9999")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "source not found"}

    app.dependency_overrides.clear()
