from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.main import app
from app.models import SourceChunk, SourceDocument


def test_canon_register_activate_active_and_history() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    SourceDocument.__table__.create(bind=engine)
    SourceChunk.__table__.create(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    upload_v1 = client.post(
        "/sources/upload",
        data={"source_type": "canon_doc"},
        files={"file": ("doc_v1.txt", b"version one", "text/plain")},
    )
    assert upload_v1.status_code == 201
    source_v1_id = upload_v1.json()["source_document"]["id"]

    register_v1 = client.post(
        f"/canon/register/{source_v1_id}",
        json={"canonical_doc_id": "canon-001", "version_label": "v1"},
    )
    assert register_v1.status_code == 200
    assert register_v1.json()["canonical_doc_id"] == "canon-001"
    assert register_v1.json()["version_label"] == "v1"

    activate_v1 = client.post(f"/canon/activate/{source_v1_id}")
    assert activate_v1.status_code == 200
    assert activate_v1.json()["is_active_canon_version"] is True

    upload_v2 = client.post(
        "/sources/upload",
        data={"source_type": "canon_doc"},
        files={"file": ("doc_v2.txt", b"version two", "text/plain")},
    )
    assert upload_v2.status_code == 201
    source_v2_id = upload_v2.json()["source_document"]["id"]

    register_v2 = client.post(
        f"/canon/register/{source_v2_id}",
        json={"canonical_doc_id": "canon-001", "version_label": "v2"},
    )
    assert register_v2.status_code == 200

    activate_v2 = client.post(f"/canon/activate/{source_v2_id}")
    assert activate_v2.status_code == 200
    assert activate_v2.json()["id"] == source_v2_id
    assert activate_v2.json()["is_active_canon_version"] is True

    active_response = client.get("/canon/active")
    assert active_response.status_code == 200
    active_docs = active_response.json()
    assert len(active_docs) == 1
    assert active_docs[0]["id"] == source_v2_id

    history_response = client.get("/canon/history/canon-001")
    assert history_response.status_code == 200
    history = history_response.json()
    assert history["canonical_doc_id"] == "canon-001"
    assert len(history["versions"]) == 2

    with TestingSessionLocal() as db:
        docs = list(
            db.scalars(
                select(SourceDocument)
                .where(SourceDocument.canonical_doc_id == "canon-001")
                .order_by(SourceDocument.id.asc())
            ).all()
        )
        assert len(docs) == 2
        assert docs[0].is_active_canon_version is False
        assert docs[1].is_active_canon_version is True

    app.dependency_overrides.clear()


def test_canon_register_and_activate_validation_errors() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    SourceDocument.__table__.create(bind=engine)
    SourceChunk.__table__.create(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    non_canon_upload = client.post(
        "/sources/upload",
        data={"source_type": "note"},
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert non_canon_upload.status_code == 201
    source_id = non_canon_upload.json()["source_document"]["id"]

    register_non_canon = client.post(
        f"/canon/register/{source_id}",
        json={"canonical_doc_id": "canon-x", "version_label": "v1"},
    )
    assert register_non_canon.status_code == 400

    activate_non_canon = client.post(f"/canon/activate/{source_id}")
    assert activate_non_canon.status_code == 400

    missing_register = client.post(
        "/canon/register/9999",
        json={"canonical_doc_id": "canon-x", "version_label": "v1"},
    )
    assert missing_register.status_code == 404

    app.dependency_overrides.clear()
