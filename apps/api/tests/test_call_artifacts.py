from collections.abc import Generator
from datetime import datetime, timezone
from io import BytesIO

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import db as db_module
from app.config import get_settings
from app.db import get_db
from app.deps import get_call_extraction_extractor
from app.main import app
from app.models import AuditEvent, CallArtifact, SourceChunk, SourceDocument, Task, TaskCandidate, TaskUpdate
from app.task_candidate_extraction import CandidateDraft


TRANSCRIPT_FIXTURE = """\
Call — Q1 planning
Decision: We will ship the beta by 2026-05-01.
Action: Owner: Jordan to send the checklist by 2026-04-15.
Blocker: waiting on legal review for the disclaimer text.
- Follow up with finance on budget cap
Next step: schedule a sync with the vendor.
"""


def _setup_client(tmp_path, monkeypatch) -> TestClient:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SOURCES_UPLOAD_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()

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

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(db_module, "SessionLocal", TestingSessionLocal)
    return TestClient(app)


def test_call_artifact_manual_notes_upload_list_detail_extract(
    tmp_path, monkeypatch
) -> None:
    client = _setup_client(tmp_path, monkeypatch)

    buf = BytesIO(TRANSCRIPT_FIXTURE.encode("utf-8"))
    up = client.post(
        "/calls/upload-artifact",
        data={"artifact_type": "manual_notes", "title": "Q1 planning"},
        files={"file": ("meeting_notes.txt", buf, "text/plain")},
    )
    assert up.status_code == 201
    aid = up.json()["call_artifact"]["id"]

    listed = client.get("/calls/artifacts")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    one = client.get(f"/calls/artifacts/{aid}")
    assert one.status_code == 200
    assert one.json()["artifact_type"] == "manual_notes"
    assert one.json()["source_document"]["source_type"] == "manual_notes"

    ext = client.post(f"/calls/artifacts/{aid}/extract-actions")
    assert ext.status_code == 200
    cands = ext.json()
    assert len(cands) >= 1
    assert cands[0]["source_document_id"] == one.json()["source_document_id"]
    assert cands[0]["call_artifact_id"] == aid
    assert "extraction_kind" in cands[0]["hints_json"] or "blocker" in cands[0]["hints_json"]

    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_call_extract_with_mock_provider(tmp_path, monkeypatch) -> None:
    client = _setup_client(tmp_path, monkeypatch)

    class MockCallExtractor:
        def extract_candidates(self, source_text: str) -> list[CandidateDraft]:
            return [
                CandidateDraft(
                    title="Mock call action",
                    description="from mock",
                    inferred_owner_name=None,
                    inferred_due_at=None,
                    fallback_due_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                    confidence=0.88,
                    extraction_kind="action_item",
                )
            ]

    app.dependency_overrides[get_call_extraction_extractor] = lambda: MockCallExtractor()

    buf = BytesIO(b"TODO: review the deck.")
    up = client.post(
        "/calls/upload-artifact",
        data={"artifact_type": "transcript"},
        files={"file": ("call.txt", buf, "text/plain")},
    )
    assert up.status_code == 201
    aid = up.json()["call_artifact"]["id"]

    ext = client.post(f"/calls/artifacts/{aid}/extract-actions")
    assert ext.status_code == 200
    titles = {c["title"] for c in ext.json()}
    assert "Mock call action" in titles

    app.dependency_overrides.pop(get_call_extraction_extractor, None)
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_summary_doc_upload(tmp_path, monkeypatch) -> None:
    client = _setup_client(tmp_path, monkeypatch)
    buf = BytesIO(b"Summary:\nDecision: Approve roadmap.\nAction: Ship MVP.")
    r = client.post(
        "/calls/upload-artifact",
        data={"artifact_type": "summary_doc"},
        files={"file": ("summary.txt", buf, "text/plain")},
    )
    assert r.status_code == 201
    assert r.json()["call_artifact"]["artifact_type"] == "summary_doc"
    app.dependency_overrides.clear()
    get_settings.cache_clear()
