"""End-to-end Week 3 integration tests.

Each test exercises one Week 3 capability through the public HTTP
surface using the mock provider. Tests are intentionally cumulative:
upload → process → extract → search → audit. They do NOT depend on a
real Postgres (semantic search and FTS are stubbed at the route layer
where SQLite cannot host the underlying types).
"""
from __future__ import annotations

from collections.abc import Generator
from io import BytesIO

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
from app.models import (
    AuditEvent,
    Blocker,
    CallArtifact,
    CanonChangeEvent,
    Delegation,
    Obstacle,
    Recommendation,
    ReviewSession,
    SourceChunk,
    SourceDocument,
    SubTask,
    Task,
    TaskCandidate,
    TaskUpdate,
)


def _setup(tmp_path, monkeypatch: pytest.MonkeyPatch):
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
    # Auto-extract is intentionally OFF in the global conftest fixture; turn
    # it on for this suite so we can verify the auto-extraction contract.
    settings.auto_extract_tasks = True

    def override_db() -> Generator[Session, None, None]:
        d = SessionTesting()
        try:
            yield d
        finally:
            d.close()

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(db_module, "SessionLocal", SessionTesting)
    return TestClient(app), SessionTesting


# ─── Day 1: transcription pipeline ─────────────────────────────────


def test_audio_upload_transcribes_and_chunks(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, SessionTesting = _setup(tmp_path, monkeypatch)

    response = client.post(
        "/sources/upload",
        data={"source_type": "transcript"},
        files={"file": ("call.mp3", b"\x00" * 64, "audio/mpeg")},
    )
    assert response.status_code == 201
    source_id = response.json()["source_document"]["id"]

    detail = client.get(f"/sources/{source_id}").json()
    assert detail["processing_status"] == "complete"
    assert detail["processing_metadata"] is not None
    assert len(detail["processing_metadata"]["segments"]) == 3

    with SessionTesting() as db:
        chunks = list(
            db.scalars(select(SourceChunk).where(SourceChunk.source_document_id == source_id)).all()
        )
        assert len(chunks) >= 1

    app.dependency_overrides.clear()


# ─── Day 1: chunked PDF processing ─────────────────────────────────


def test_pdf_upload_processes_in_batches(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, SessionTesting = _setup(tmp_path, monkeypatch)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    for i in range(50):
        pdf.drawString(72, 720, f"Page {i} content with action items for property review")
        pdf.showPage()
    pdf.save()

    response = client.post(
        "/sources/upload",
        data={"source_type": "thread_export"},
        files={"file": ("big.pdf", buffer.getvalue(), "application/pdf")},
    )
    assert response.status_code == 201
    source_id = response.json()["source_document"]["id"]

    detail = client.get(f"/sources/{source_id}").json()
    assert detail["processing_status"] == "complete"
    assert detail["pages_total"] == 50
    assert detail["pages_processed"] == 50

    with SessionTesting() as db:
        chunks = list(
            db.scalars(select(SourceChunk).where(SourceChunk.source_document_id == source_id)).all()
        )
        assert len(chunks) >= 5  # at least one chunk per batch of 10 pages

    app.dependency_overrides.clear()


# ─── Day 2: enhanced task extraction ───────────────────────────────


def test_auto_extract_emits_rich_candidates(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _setup(tmp_path, monkeypatch)

    note = "Action: Owner: Alex follow up by 2026-04-30 — urgent\nDecision: monthly invoice cadence\n".encode("utf-8")
    response = client.post(
        "/sources/upload",
        data={"source_type": "note"},
        files={"file": ("d2-note.txt", note, "text/plain")},
    )
    assert response.status_code == 201
    source_id = response.json()["source_document"]["id"]

    candidates = client.get("/task-candidates?review_status=pending_review").json()
    mine = [c for c in candidates if c["source_document_id"] == source_id]
    assert len(mine) >= 1
    llm = [c for c in mine if (c.get("hints_json") or {}).get("llm_extracted")]
    assert llm, "expected an LLM-extracted candidate with rich fields"
    sample = llm[0]
    assert sample["suggested_priority"] in {"low", "medium", "high"}
    assert sample["canon_alignment"]
    assert (sample["hints_json"] or {}).get("extraction_kind") in {
        "action_item", "decision", "discussion",
    }

    app.dependency_overrides.clear()


def test_transcript_auto_extract_includes_speaker_and_timestamp(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _setup(tmp_path, monkeypatch)

    response = client.post(
        "/sources/upload",
        data={"source_type": "transcript"},
        files={"file": ("call.mp3", b"\x00\x01" * 32, "audio/mpeg")},
    )
    source_id = response.json()["source_document"]["id"]

    candidates = client.get("/task-candidates?review_status=pending_review").json()
    mine = [c for c in candidates if c["source_document_id"] == source_id]
    llm = [c for c in mine if (c.get("hints_json") or {}).get("llm_extracted")]
    assert any(c.get("source_timestamp") for c in llm), "expected at least one candidate with a source_timestamp"
    assert any(c.get("inferred_owner_name") for c in llm), "expected at least one candidate with an owner inferred from speaker labels"

    app.dependency_overrides.clear()


# ─── Day 2: canon change detection ─────────────────────────────────


def test_canon_v1_then_v2_creates_change_event(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _setup(tmp_path, monkeypatch)

    v1 = client.post(
        "/sources/upload",
        data={"source_type": "canon_doc"},
        files={"file": ("v1.txt", b"vendor onboarding standard v1", "text/plain")},
    )
    v1_id = v1.json()["source_document"]["id"]
    client.post(
        f"/canon/register/{v1_id}",
        json={"canonical_doc_id": "wk3-vendor", "version_label": "v1"},
    )
    client.post(f"/canon/activate/{v1_id}")

    # Seed an active task that mentions the canon id.
    task_resp = client.post(
        "/tasks",
        json={
            "title": "Onboard new vendor referencing wk3-vendor",
            "description": "uses the wk3-vendor checklist",
            "objective": "ship without service drift",
            "standard": "Execution",
            "status": "in_progress",
            "priority": "medium",
            "owner_name": "Alex",
            "assigner_name": "Manager",
        },
    )
    task_id = task_resp.json()["id"]

    v2 = client.post(
        "/sources/upload",
        data={"source_type": "canon_doc"},
        files={"file": ("v2.txt", b"vendor onboarding standard v2 with stricter timelines", "text/plain")},
    )
    v2_id = v2.json()["source_document"]["id"]
    client.post(
        f"/canon/register/{v2_id}",
        json={"canonical_doc_id": "wk3-vendor", "version_label": "v2"},
    )
    client.post(f"/canon/activate/{v2_id}")

    listed = client.get("/canon/changes").json()
    assert listed["unreviewed_count"] >= 1
    event = listed["events"][0]
    assert event["canon_doc_id"] == "wk3-vendor"
    assert task_id in event["affected_task_ids"]

    task_after = client.get(f"/tasks/{task_id}").json()
    assert task_after["canon_update_pending"] is True

    app.dependency_overrides.clear()


# ─── Day 3: search ─────────────────────────────────────────────────


def test_search_route_orchestrator_returns_unified_envelope(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In SQLite the FTS columns don't exist; we stub the orchestrator
    so this test exercises the route + envelope without needing PG."""
    client, _ = _setup(tmp_path, monkeypatch)

    from app.services import search as search_module

    stub_payload = {
        "results": [
            {
                "id": 1, "type": "task", "title": "Audit cycle task",
                "snippet": "<mark>audit</mark>", "relevance": 0.9,
                "url": "/tasks?selected=1", "metadata": {"status": "in_progress"},
            }
        ],
        "total": 1, "type_counts": {"tasks": 1}, "mode": "keyword",
    }
    monkeypatch.setattr(search_module, "search", lambda *a, **k: stub_payload)

    resp = client.get("/search?q=audit&type=tasks")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "keyword"
    assert body["type_filter"] == "tasks"
    assert body["total"] == 1
    assert body["results"][0]["snippet"] == "<mark>audit</mark>"

    app.dependency_overrides.clear()


# ─── Day 4: audit covers the full Week-3 surface ───────────────────


def test_source_pipeline_emits_uploaded_and_processed_audit_events(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, SessionTesting = _setup(tmp_path, monkeypatch)

    response = client.post(
        "/sources/upload",
        data={"source_type": "note"},
        files={"file": ("audit.txt", b"hello world", "text/plain")},
    )
    source_id = response.json()["source_document"]["id"]

    audit = client.get(f"/audit?entity_type=source&entity_id={source_id}").json()
    actions = {e["action"] for e in audit["events"]}
    assert "uploaded" in actions
    assert "source_processed" in actions

    app.dependency_overrides.clear()


def test_canon_activation_audit_event_fired(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _setup(tmp_path, monkeypatch)

    up = client.post(
        "/sources/upload",
        data={"source_type": "canon_doc"},
        files={"file": ("c.txt", b"first canon version", "text/plain")},
    )
    cid = up.json()["source_document"]["id"]
    client.post(
        f"/canon/register/{cid}",
        json={"canonical_doc_id": "audit-canon", "version_label": "v1"},
    )
    client.post(f"/canon/activate/{cid}")

    audit = client.get(f"/audit?entity_type=source&entity_id={cid}").json()
    actions = {e["action"] for e in audit["events"]}
    assert "canon_activated" in actions

    app.dependency_overrides.clear()
