"""Tests for recommendation modes (standard vs unblock) and history endpoint.

These tests don't call the real LLM — they use the in-process MockAIProvider
via the default provider factory, which returns deterministic placeholder
drafts for both modes.
"""
from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.main import app
from app.models import (
    AuditEvent,
    Blocker,
    Delegation,
    Recommendation,
    ReviewSession,
    SourceChunk,
    SourceDocument,
    Task,
    TaskUpdate,
)


def _build_test_db() -> tuple[sessionmaker, object]:
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
    AuditEvent.__table__.create(bind=engine)
    return TestingSessionLocal, engine


def test_standard_mode_returns_recommendation_context_meta() -> None:
    TestingSessionLocal, _ = _build_test_db()

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    task_resp = client.post(
        "/tasks",
        json={
            "title": "Standard task",
            "description": "Simple test task",
            "objective": "Do the thing",
            "standard": "Consistency",
            "status": "up_next",
            "priority": "medium",
            "owner_name": "alex",
            "assigner_name": "jordan",
            "due_at": None,
            "source_confidence": 0.9,
        },
    )
    assert task_resp.status_code == 201
    task_id = task_resp.json()["id"]

    rec = client.post(f"/tasks/{task_id}/recommendation")
    assert rec.status_code == 200
    body = rec.json()
    assert body["recommendation_type"] == "standard"
    assert body["recommendation_context"] is not None
    assert body["recommendation_context"]["blocker_active"] is False
    assert body["unblock_analysis"] is None
    assert len(body["viable_options"]) >= 2

    app.dependency_overrides.clear()


def test_blocked_task_returns_unblock_analysis() -> None:
    TestingSessionLocal, _ = _build_test_db()

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    task_resp = client.post(
        "/tasks",
        json={
            "title": "Stuck task",
            "description": "Has been stuck for a while",
            "objective": "Unblock this",
            "standard": "Accountability",
            "status": "blocked",
            "priority": "high",
            "owner_name": "alex",
            "assigner_name": "jordan",
            "due_at": None,
            "source_confidence": 0.9,
        },
    )
    assert task_resp.status_code == 201
    task_id = task_resp.json()["id"]

    # Record an actual open blocker on the task so the context reflects it.
    client.post(
        f"/tasks/{task_id}/block",
        json={
            "blocker_type": "dependency",
            "blocker_reason": "Waiting on vendor response",
            "severity": "high",
        },
    )

    rec = client.post(f"/tasks/{task_id}/recommendation")
    assert rec.status_code == 200
    body = rec.json()
    assert body["recommendation_type"] == "unblock"
    assert body["recommendation_context"]["blocker_active"] is True

    unblock = body["unblock_analysis"]
    assert unblock is not None
    assert unblock["blocker_summary"]
    assert unblock["root_cause_analysis"]
    assert len(unblock["alternatives"]) == 3
    for alt in unblock["alternatives"]:
        assert alt["path"]
        assert alt["first_step"]
        assert alt["aligned_standard"]
    assert unblock["recommended_path"]

    # Standard top-level fields are still populated for backward compat.
    assert body["objective"]
    assert body["next_action"]
    assert len(body["viable_options"]) == 3

    app.dependency_overrides.clear()


def test_recommendation_history_endpoint_returns_newest_first() -> None:
    TestingSessionLocal, _ = _build_test_db()

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    task_resp = client.post(
        "/tasks",
        json={
            "title": "History task",
            "description": "test",
            "objective": "o",
            "standard": "s",
            "status": "up_next",
            "priority": "medium",
            "owner_name": "alex",
            "assigner_name": "jordan",
            "due_at": None,
            "source_confidence": 0.9,
        },
    )
    task_id = task_resp.json()["id"]

    # First recommendation.
    r1 = client.post(f"/tasks/{task_id}/recommendation")
    assert r1.status_code == 200
    first_id = r1.json()["id"]

    # Second call within the cache window AND same context hash → cached
    # (same id returned).
    r1b = client.post(f"/tasks/{task_id}/recommendation")
    assert r1b.json()["id"] == first_id

    # Add an update → context hash changes → new recommendation.
    client.post(
        f"/tasks/{task_id}/updates",
        json={
            "update_type": "note",
            "summary": "Tried the vendor, they said next week.",
            "what_happened": "",
            "options_considered": "",
            "steps_taken": "",
            "next_step": "",
            "created_by": "alex",
        },
    )
    r2 = client.post(f"/tasks/{task_id}/recommendation")
    assert r2.status_code == 200
    assert r2.json()["id"] != first_id

    # History endpoint should now return both, newest first.
    hist = client.get(f"/tasks/{task_id}/recommendations")
    assert hist.status_code == 200
    rows = hist.json()
    assert len(rows) == 2
    assert rows[0]["id"] == r2.json()["id"]
    assert rows[1]["id"] == first_id
    assert all(r["recommendation_type"] == "standard" for r in rows)

    app.dependency_overrides.clear()
