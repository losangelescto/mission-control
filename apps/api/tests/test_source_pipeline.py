"""End-to-end source pipeline tests.

The pipeline runs as a FastAPI BackgroundTask. TestClient awaits those
tasks before returning, so the upload response sees status="queued" but
any subsequent call sees the BG task's effects.
"""
from __future__ import annotations

from collections.abc import Generator
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import db as db_module
from app.config import get_settings
from app.db import get_db
from app.main import app
from app.models import SourceChunk, SourceDocument
from app.services import source_pipeline


def _setup_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, sessionmaker]:
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
    return TestClient(app), TestingSessionLocal


def test_text_upload_runs_in_background_and_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _setup_client(tmp_path, monkeypatch)

    response = client.post(
        "/sources/upload",
        data={"source_type": "note"},
        files={"file": ("note.txt", b"line one\nline two\nline three", "text/plain")},
    )
    assert response.status_code == 201
    source_id = response.json()["source_document"]["id"]

    # Background task has run by the time TestClient returns.
    detail = client.get(f"/sources/{source_id}").json()
    assert detail["processing_status"] == "complete"
    assert detail["extracted_text"].startswith("line one")

    status = client.get(f"/sources/{source_id}/status").json()
    assert status["processing_status"] == "complete"
    assert status["pages_total"] == 0  # text files have no pages

    app.dependency_overrides.clear()


def test_pdf_upload_records_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, TestingSessionLocal = _setup_client(tmp_path, monkeypatch)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    for page in range(3):
        pdf.drawString(72, 720, f"Page {page} content with action items")
        pdf.showPage()
    pdf.save()

    response = client.post(
        "/sources/upload",
        data={"source_type": "thread_export"},
        files={"file": ("multi.pdf", buffer.getvalue(), "application/pdf")},
    )
    assert response.status_code == 201
    source_id = response.json()["source_document"]["id"]

    detail = client.get(f"/sources/{source_id}").json()
    assert detail["processing_status"] == "complete"
    assert detail["pages_total"] == 3
    assert detail["pages_processed"] == 3

    with TestingSessionLocal() as db:
        chunks = list(
            db.scalars(select(SourceChunk).where(SourceChunk.source_document_id == source_id)).all()
        )
        assert len(chunks) >= 1

    app.dependency_overrides.clear()


def test_audio_upload_uses_mock_transcription(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, TestingSessionLocal = _setup_client(tmp_path, monkeypatch)

    response = client.post(
        "/sources/upload",
        data={"source_type": "transcript"},
        files={"file": ("call.mp3", b"\x00\x01" * 64, "audio/mpeg")},
    )
    assert response.status_code == 201
    source_id = response.json()["source_document"]["id"]

    detail = client.get(f"/sources/{source_id}").json()
    assert detail["processing_status"] == "complete"
    assert detail["processing_metadata"] is not None
    metadata = detail["processing_metadata"]
    assert metadata["duration_seconds"] > 0
    assert len(metadata["segments"]) == 3
    assert "Speaker 1" in detail["extracted_text"]

    status = client.get(f"/sources/{source_id}/status").json()
    assert status["transcription_segments_count"] == 3
    assert status["duration_seconds"] is not None and status["duration_seconds"] > 0

    app.dependency_overrides.clear()


def test_unsupported_extension_rejected_at_upload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _setup_client(tmp_path, monkeypatch)

    response = client.post(
        "/sources/upload",
        data={"source_type": "note"},
        files={"file": ("photo.png", b"fake", "image/png")},
    )
    assert response.status_code == 400
    assert "unsupported file type" in response.json()["detail"]

    app.dependency_overrides.clear()


def test_status_route_returns_404_for_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _setup_client(tmp_path, monkeypatch)

    response = client.get("/sources/9999/status")
    assert response.status_code == 404

    app.dependency_overrides.clear()


def test_audio_too_long_marked_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the transcription duration exceeds the cap, the source is marked failed."""
    client, _ = _setup_client(tmp_path, monkeypatch)
    settings = get_settings()
    monkeypatch.setattr(settings, "max_audio_duration_seconds", 1)

    response = client.post(
        "/sources/upload",
        data={"source_type": "transcript"},
        files={"file": ("long.mp3", b"\x00" * 16, "audio/mpeg")},
    )
    assert response.status_code == 201
    source_id = response.json()["source_document"]["id"]

    detail = client.get(f"/sources/{source_id}").json()
    assert detail["processing_status"] == "failed"
    assert "exceeds limit" in detail["processing_error"]

    app.dependency_overrides.clear()


def test_process_source_handles_missing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Calling process_source on a record whose file was deleted marks it failed."""
    client, TestingSessionLocal = _setup_client(tmp_path, monkeypatch)

    response = client.post(
        "/sources/upload",
        data={"source_type": "note"},
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    source_id = response.json()["source_document"]["id"]

    with TestingSessionLocal() as db:
        source = db.get(SourceDocument, source_id)
        assert source is not None
        Path(source.source_path).unlink()
        # Reset to queued and run the pipeline directly.
        source.processing_status = "queued"
        db.commit()
        source_pipeline.process_source(db, source_id)
        db.refresh(source)
        assert source.processing_status == "failed"
        assert "missing" in (source.processing_error or "")

    app.dependency_overrides.clear()


# ─── Fix 4: auto-extract regression suite ────────────────────────────


def _setup_pipeline_with_full_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[TestClient, sessionmaker]:
    """Pipeline + full task/extraction schema so auto-extract has somewhere
    to write candidates and audit rows."""
    from app.models import (
        AuditEvent, Blocker, CallArtifact, CanonChangeEvent, Delegation,
        Obstacle, Recommendation, ReviewSession, SubTask, Task, TaskCandidate,
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
    return TestClient(app), SessionTesting


def _enable_auto_extract(monkeypatch: pytest.MonkeyPatch) -> None:
    """Override the autouse conftest fixture for tests that need it on."""
    settings = get_settings()
    monkeypatch.setattr(settings, "auto_extract_tasks", True)


def test_auto_extract_runs_on_text_source_upload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, SessionTesting = _setup_pipeline_with_full_schema(tmp_path, monkeypatch)
    _enable_auto_extract(monkeypatch)

    response = client.post(
        "/sources/upload",
        data={"source_type": "note"},
        files={
            "file": (
                "auto-extract.txt",
                b"Action: Owner: Alex follow up by 2026-04-30 - urgent",
                "text/plain",
            )
        },
    )
    assert response.status_code == 201
    source_id = response.json()["source_document"]["id"]

    from app.models import TaskCandidate

    with SessionTesting() as db:
        candidates = list(
            db.scalars(
                select(TaskCandidate).where(TaskCandidate.source_document_id == source_id)
            ).all()
        )
        assert len(candidates) >= 1, "auto-extract should have created candidates"

    app.dependency_overrides.clear()


def test_auto_extract_skips_canon_doc_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, SessionTesting = _setup_pipeline_with_full_schema(tmp_path, monkeypatch)
    _enable_auto_extract(monkeypatch)

    response = client.post(
        "/sources/upload",
        data={"source_type": "canon_doc"},
        files={
            "file": (
                "fix4-canon.txt",
                b"Action: Owner: Alex must follow up urgently to test extraction skip.",
                "text/plain",
            )
        },
    )
    source_id = response.json()["source_document"]["id"]

    from app.models import TaskCandidate

    with SessionTesting() as db:
        candidates = list(
            db.scalars(
                select(TaskCandidate).where(TaskCandidate.source_document_id == source_id)
            ).all()
        )
        assert candidates == [], "canon_doc sources must skip auto-extraction"

    app.dependency_overrides.clear()


def test_auto_extract_emits_source_processed_audit_with_candidate_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, SessionTesting = _setup_pipeline_with_full_schema(tmp_path, monkeypatch)
    _enable_auto_extract(monkeypatch)

    response = client.post(
        "/sources/upload",
        data={"source_type": "note"},
        files={
            "file": (
                "audit-count.txt",
                b"Action: Owner: Pat follow up with the lender by 2026-05-15 - urgent",
                "text/plain",
            )
        },
    )
    source_id = response.json()["source_document"]["id"]

    from app.models import AuditEvent

    with SessionTesting() as db:
        rows = list(
            db.scalars(
                select(AuditEvent)
                .where(AuditEvent.entity_type == "source")
                .where(AuditEvent.entity_id == str(source_id))
                .where(AuditEvent.action == "source_processed")
            ).all()
        )
        assert len(rows) == 1
        md = rows[0].event_metadata or {}
        count = md.get("extracted_candidate_count")
        assert isinstance(count, int) and count >= 1, (
            f"audit metadata should carry extracted_candidate_count >= 1, got {count!r}"
        )

    app.dependency_overrides.clear()


def test_auto_extract_disabled_when_config_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When AUTO_EXTRACT_TASKS=false, no candidates are auto-created."""
    client, SessionTesting = _setup_pipeline_with_full_schema(tmp_path, monkeypatch)
    settings = get_settings()
    monkeypatch.setattr(settings, "auto_extract_tasks", False)

    response = client.post(
        "/sources/upload",
        data={"source_type": "note"},
        files={
            "file": (
                "off.txt",
                b"Action: should not auto-extract because the flag is off.",
                "text/plain",
            )
        },
    )
    source_id = response.json()["source_document"]["id"]

    from app.models import AuditEvent, TaskCandidate

    with SessionTesting() as db:
        candidates = list(
            db.scalars(
                select(TaskCandidate).where(TaskCandidate.source_document_id == source_id)
            ).all()
        )
        assert candidates == []

        # The source_processed audit event still fires; its candidate count
        # is None because extraction was skipped (not zero, which would
        # mean it ran and produced nothing).
        rows = list(
            db.scalars(
                select(AuditEvent)
                .where(AuditEvent.entity_type == "source")
                .where(AuditEvent.entity_id == str(source_id))
                .where(AuditEvent.action == "source_processed")
            ).all()
        )
        assert len(rows) == 1
        md = rows[0].event_metadata or {}
        assert md.get("extracted_candidate_count") is None

    app.dependency_overrides.clear()
