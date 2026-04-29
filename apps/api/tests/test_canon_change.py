"""Tests for canon-change detection + the canon-changes routes."""
from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import db as db_module
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
from app.services.canon_change import detect_canon_change


def _setup_full_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionTesting = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    SourceDocument.__table__.create(bind=engine)
    SourceChunk.__table__.create(bind=engine)
    Task.__table__.create(bind=engine)
    TaskUpdate.__table__.create(bind=engine)
    TaskCandidate.__table__.create(bind=engine)
    CallArtifact.__table__.create(bind=engine)
    AuditEvent.__table__.create(bind=engine)
    Blocker.__table__.create(bind=engine)
    Delegation.__table__.create(bind=engine)
    ReviewSession.__table__.create(bind=engine)
    Recommendation.__table__.create(bind=engine)
    SubTask.__table__.create(bind=engine)
    Obstacle.__table__.create(bind=engine)
    CanonChangeEvent.__table__.create(bind=engine)
    return engine, SessionTesting


def _seed_active_task(db: Session, *, title: str, description: str = "") -> Task:
    task = Task(
        title=title,
        description=description,
        objective="o",
        standard="s",
        status="in_progress",
        priority="medium",
        owner_name="Alex",
        assigner_name="Manager",
        due_at=None,
        source_confidence=None,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _seed_canon_versions(db: Session, *, doc_id: str) -> tuple[SourceDocument, SourceDocument]:
    prev = SourceDocument(
        filename="canon_v1.txt",
        source_type="canon_doc",
        canonical_doc_id=doc_id,
        version_label="v1",
        is_active_canon_version=False,
        extracted_text="Original wording for vendor onboarding.",
        source_path="inline:canon_v1.txt",
    )
    new = SourceDocument(
        filename="canon_v2.txt",
        source_type="canon_doc",
        canonical_doc_id=doc_id,
        version_label="v2",
        is_active_canon_version=True,
        extracted_text="Revised wording for vendor onboarding with stricter timelines.",
        source_path="inline:canon_v2.txt",
    )
    db.add_all([prev, new])
    db.commit()
    db.refresh(prev)
    db.refresh(new)
    return prev, new


def test_detect_canon_change_creates_event_and_marks_task() -> None:
    _, SessionTesting = _setup_full_db()
    db: Session = SessionTesting()

    prev, new = _seed_canon_versions(db, doc_id="canon-vendor")
    affected_task = _seed_active_task(
        db,
        title="Onboard new HVAC vendor",
        description="Coordinate paperwork referencing canon-vendor checklist.",
    )

    event = detect_canon_change(db, new_source=new, previous_source=prev)
    db.commit()
    assert event is not None
    assert event.canon_doc_id == "canon-vendor"
    assert event.previous_source_id == prev.id
    assert event.new_source_id == new.id
    # The body-text mention path should pick up the affected task.
    assert affected_task.id in (event.affected_task_ids or [])
    db.refresh(affected_task)
    assert affected_task.canon_update_pending is True
    db.close()


def test_detect_canon_change_returns_none_without_previous() -> None:
    _, SessionTesting = _setup_full_db()
    db: Session = SessionTesting()
    _, new = _seed_canon_versions(db, doc_id="canon-orphan")
    event = detect_canon_change(db, new_source=new, previous_source=None)
    assert event is None
    db.close()


def test_canon_changes_routes_list_get_acknowledge(monkeypatch: pytest.MonkeyPatch) -> None:
    engine, SessionTesting = _setup_full_db()

    def override_get_db() -> Generator[Session, None, None]:
        d = SessionTesting()
        try:
            yield d
        finally:
            d.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(db_module, "SessionLocal", SessionTesting)

    db: Session = SessionTesting()
    prev, new = _seed_canon_versions(db, doc_id="canon-routes")
    affected = _seed_active_task(
        db,
        title="Update vendor checklist",
        description="references canon-routes",
    )
    affected_id = affected.id
    detect_canon_change(db, new_source=new, previous_source=prev)
    db.commit()
    db.close()

    client = TestClient(app)

    listed = client.get("/canon/changes").json()
    assert listed["unreviewed_count"] == 1
    assert len(listed["events"]) == 1
    event_id = listed["events"][0]["id"]

    detail = client.get(f"/canon/changes/{event_id}").json()
    assert detail["canon_doc_id"] == "canon-routes"
    assert detail["new_source_filename"] == "canon_v2.txt"
    assert detail["previous_source_filename"] == "canon_v1.txt"
    titles = [task["title"] for task in detail["affected_tasks"]]
    assert "Update vendor checklist" in titles

    # Task surfaces canon_update_pending in its TaskResponse shape.
    task_resp = client.get(f"/tasks/{affected_id}").json()
    assert task_resp["canon_update_pending"] is True

    ack = client.post(f"/canon/changes/{event_id}/acknowledge").json()
    assert ack["reviewed"] is True

    # After ack, the affected task's pending flag is cleared.
    task_resp_after = client.get(f"/tasks/{affected_id}").json()
    assert task_resp_after["canon_update_pending"] is False

    listed_after = client.get("/canon/changes").json()
    assert listed_after["unreviewed_count"] == 0

    app.dependency_overrides.clear()


def test_acknowledge_404_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    engine, SessionTesting = _setup_full_db()

    def override_get_db() -> Generator[Session, None, None]:
        d = SessionTesting()
        try:
            yield d
        finally:
            d.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(db_module, "SessionLocal", SessionTesting)
    client = TestClient(app)

    resp = client.post("/canon/changes/9999/acknowledge")
    assert resp.status_code == 404
    app.dependency_overrides.clear()
