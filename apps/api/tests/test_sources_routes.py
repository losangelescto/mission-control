from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db import get_db
from app.main import app
from app.models import SourceChunk, SourceDocument


def test_sources_upload_and_read_routes(tmp_path) -> None:  # type: ignore[no-untyped-def]
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
    assert payload["chunk_count"] >= 1

    list_response = client.get("/sources")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    source_id = payload["source_document"]["id"]
    get_response = client.get(f"/sources/{source_id}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == source_id

    with TestingSessionLocal() as db:
        chunks = list(
            db.scalars(select(SourceChunk).where(SourceChunk.source_document_id == source_id)).all()
        )
        assert len(chunks) >= 1

    app.dependency_overrides.clear()


def test_sources_upload_rejects_unsupported_extension(tmp_path) -> None:  # type: ignore[no-untyped-def]
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
    client = TestClient(app)

    upload_response = client.post(
        "/sources/upload",
        data={"source_type": "note"},
        files={"file": ("image.png", b"fake", "image/png")},
    )
    assert upload_response.status_code == 400
    assert "unsupported file type" in upload_response.json()["detail"]

    app.dependency_overrides.clear()
