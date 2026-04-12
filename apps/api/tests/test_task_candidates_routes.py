from collections.abc import Generator
from io import BytesIO

from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db import get_db
from app.main import app
from app.models import AuditEvent, CallArtifact, SourceChunk, SourceDocument, Task, TaskCandidate, TaskUpdate


def _build_pdf_bytes(text: str) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 720, text)
    pdf.save()
    return buffer.getvalue()


def test_task_candidate_extraction_approve_reject_flow(tmp_path) -> None:  # type: ignore[no-untyped-def]
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    SourceDocument.__table__.create(bind=engine)
    CallArtifact.__table__.create(bind=engine)
    SourceChunk.__table__.create(bind=engine)
    TaskCandidate.__table__.create(bind=engine)
    Task.__table__.create(bind=engine)
    TaskUpdate.__table__.create(bind=engine)
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

    upload = client.post(
        "/sources/upload",
        data={"source_type": "note"},
        files={
            "file": (
                "candidate_note.txt",
                b"TODO: Owner: Alex follow up with lender by 2026-04-10 urgent dependency risk",
                "text/plain",
            )
        },
    )
    assert upload.status_code == 201
    source_id = upload.json()["source_document"]["id"]

    extract = client.post(f"/sources/{source_id}/extract-task-candidates")
    assert extract.status_code == 200
    candidates = extract.json()
    assert len(candidates) >= 1
    first = candidates[0]
    assert first["source_document_id"] == source_id
    assert first["review_status"] == "pending_review"
    assert "urgency_hints" in first["description"]
    assert "blocker_hints" in first["description"]
    assert "recurrence_hints" in first["description"]
    assert first["inferred_owner_name"] == "Alex"
    assert first["inferred_due_at"] is not None
    assert first["fallback_due_at"] is not None

    list_pending = client.get("/task-candidates", params={"review_status": "pending_review"})
    assert list_pending.status_code == 200
    assert len(list_pending.json()) >= 1

    approve = client.post(f"/task-candidates/{first['id']}/approve")
    assert approve.status_code == 200
    approved_task = approve.json()
    assert approved_task["title"]
    assert approved_task["status"] == "backlog"

    with TestingSessionLocal() as db:
        updated_candidate = db.get(TaskCandidate, first["id"])
        assert updated_candidate is not None
        assert updated_candidate.review_status == "approved"
        task_updates = list(db.scalars(select(TaskUpdate).where(TaskUpdate.task_id == approved_task["id"])).all())
        assert len(task_updates) == 1
        assert task_updates[0].what_happened
        assert task_updates[0].options_considered
        assert task_updates[0].steps_taken
        assert task_updates[0].next_step

    upload_reject = client.post(
        "/sources/upload",
        data={"source_type": "note"},
        files={"file": ("reject_note.txt", b"TODO: task archive old thread notes", "text/plain")},
    )
    assert upload_reject.status_code == 201
    reject_source_id = upload_reject.json()["source_document"]["id"]
    extract_reject = client.post(f"/sources/{reject_source_id}/extract-task-candidates")
    assert extract_reject.status_code == 200
    reject_target = extract_reject.json()[0]["id"]

    reject = client.post(f"/task-candidates/{reject_target}/reject", json={"reason": "not actionable"})
    assert reject.status_code == 200
    assert reject.json()["review_status"] == "rejected"
    assert "rejection_reason: not actionable" in reject.json()["description"]

    app.dependency_overrides.clear()


def test_task_candidate_extraction_with_pdf_fixture(tmp_path) -> None:  # type: ignore[no-untyped-def]
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    SourceDocument.__table__.create(bind=engine)
    CallArtifact.__table__.create(bind=engine)
    SourceChunk.__table__.create(bind=engine)
    TaskCandidate.__table__.create(bind=engine)
    Task.__table__.create(bind=engine)
    TaskUpdate.__table__.create(bind=engine)
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

    pdf_bytes = _build_pdf_bytes("Action: owner: Taylor task complete monthly review every week")
    upload = client.post(
        "/sources/upload",
        data={"source_type": "thread_export"},
        files={"file": ("thread.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload.status_code == 201
    source_id = upload.json()["source_document"]["id"]

    extract = client.post(f"/sources/{source_id}/extract-task-candidates")
    assert extract.status_code == 200
    extracted = extract.json()
    assert len(extracted) >= 1
    assert any("recurrence_hints" in c["description"] for c in extracted)

    app.dependency_overrides.clear()
