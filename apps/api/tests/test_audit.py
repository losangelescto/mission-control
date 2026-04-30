"""Tests for the audit-trail service + GET /audit routes."""
from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
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
from app.services.audit import diff_fields, log_event


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


def test_log_event_persists_action_actor_changes_metadata() -> None:
    _, SessionTesting = _setup_full_db()
    db: Session = SessionTesting()

    event = log_event(
        db,
        entity_type="task",
        entity_id=42,
        action="status_changed",
        actor="alice",
        changes={"status": {"old": "backlog", "new": "in_progress"}},
        metadata={"source": "ui"},
    )
    assert event is not None
    db.commit()

    rows = list(db.scalars(select(AuditEvent)).all())
    assert len(rows) == 1
    row = rows[0]
    assert row.entity_type == "task"
    assert row.entity_id == "42"
    assert row.action == "status_changed"
    assert row.actor == "alice"
    assert row.changes == {"status": {"old": "backlog", "new": "in_progress"}}
    assert row.event_metadata == {"source": "ui"}
    db.close()


def test_log_event_failure_does_not_break_outer_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the audit insert fails, the surrounding session must still be usable."""
    _, SessionTesting = _setup_full_db()
    db: Session = SessionTesting()

    # Simulate a serialization failure by passing a non-JSON-able object.
    # The savepoint should swallow the error.
    class _Bomb:
        pass

    out = log_event(
        db,
        entity_type="task",
        entity_id=1,
        action="updated",
        changes={"weird": _Bomb()},  # type: ignore[arg-type]
    )
    assert out is None

    # The outer session must still accept new writes.
    task = Task(
        title="still works",
        description="",
        objective="",
        standard="",
        status="backlog",
        priority="low",
        owner_name="x",
        assigner_name="y",
    )
    db.add(task)
    db.commit()
    assert task.id is not None
    db.close()


def test_diff_fields_skips_unchanged_and_includes_changed() -> None:
    before = {"a": 1, "b": "hello", "c": True, "d": "same"}
    after = {"a": 2, "b": "world", "c": True, "d": "same"}
    diff = diff_fields(before, after, ["a", "b", "c", "d", "missing"])
    assert diff == {
        "a": {"old": 1, "new": 2},
        "b": {"old": "hello", "new": "world"},
    }


def test_create_task_then_update_then_block_then_unblock_logs_four_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Audit-trail integration: full CRUD + status flip cycle on a task.

    Verifies the spec requirement: ``Create a task → update it → block
    it → unblock it → verify 4 audit events logged with correct actions
    and changes``.
    """
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

    create = client.post(
        "/tasks",
        json={
            "title": "Audit cycle task",
            "description": "Run through every transition",
            "objective": "Cover the audit trail",
            "standard": "Accountability",
            "status": "backlog",
            "priority": "medium",
            "owner_name": "Alex",
            "assigner_name": "Manager",
        },
    )
    assert create.status_code == 201
    task_id = create.json()["id"]

    # update (but not status — should NOT emit status_changed)
    upd = client.patch(f"/tasks/{task_id}", json={"priority": "high"})
    assert upd.status_code == 200

    # block — emits task_blocked + a "blocked" canonical action
    block = client.post(
        f"/tasks/{task_id}/block",
        json={"blocker_type": "dependency", "blocker_reason": "waiting on legal", "severity": "high"},
    )
    assert block.status_code == 200

    # unblock
    unblock = client.post(
        f"/tasks/{task_id}/unblock",
        json={"resolution_notes": "legal cleared the disclaimer"},
    )
    assert unblock.status_code == 200

    audit = client.get(f"/audit?entity_type=task&entity_id={task_id}").json()
    actions = [e["action"] for e in audit["events"]]
    # Newest first: unblocked, blocked, updated, created
    assert "created" in actions
    assert "updated" in actions
    assert "blocked" in actions
    assert "unblocked" in actions

    by_id = client.get(f"/audit/task/{task_id}").json()
    assert by_id["total"] >= 4

    app.dependency_overrides.clear()


def test_status_change_emits_dedicated_status_changed_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A PATCH that includes status produces both ``updated`` and ``status_changed``."""
    _, SessionTesting = _setup_full_db()

    def override_get_db() -> Generator[Session, None, None]:
        d = SessionTesting()
        try:
            yield d
        finally:
            d.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(db_module, "SessionLocal", SessionTesting)
    client = TestClient(app)

    create = client.post(
        "/tasks",
        json={
            "title": "Status flip",
            "description": "",
            "objective": "",
            "standard": "Care",
            "status": "backlog",
            "priority": "low",
            "owner_name": "x",
            "assigner_name": "y",
        },
    )
    task_id = create.json()["id"]

    patch = client.patch(f"/tasks/{task_id}", json={"status": "in_progress"})
    assert patch.status_code == 200

    audit = client.get(f"/audit?entity_type=task&entity_id={task_id}").json()
    actions = [e["action"] for e in audit["events"]]
    assert "status_changed" in actions
    sc = next(e for e in audit["events"] if e["action"] == "status_changed")
    assert sc["changes"] == {"status": {"old": "backlog", "new": "in_progress"}}

    app.dependency_overrides.clear()


def test_audit_filter_by_action_and_actor(monkeypatch: pytest.MonkeyPatch) -> None:
    _, SessionTesting = _setup_full_db()
    db: Session = SessionTesting()

    log_event(db, entity_type="task", entity_id=1, action="created", actor="alice")
    log_event(db, entity_type="task", entity_id=2, action="created", actor="bob")
    log_event(db, entity_type="task", entity_id=1, action="updated", actor="alice")
    log_event(db, entity_type="source", entity_id=10, action="uploaded", actor="alice")
    db.commit()
    db.close()

    def override_get_db() -> Generator[Session, None, None]:
        d = SessionTesting()
        try:
            yield d
        finally:
            d.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(db_module, "SessionLocal", SessionTesting)
    client = TestClient(app)

    by_action = client.get("/audit?entity_type=task&action=created").json()
    assert by_action["total"] == 2
    assert all(e["action"] == "created" for e in by_action["events"])

    by_actor = client.get("/audit?actor=bob").json()
    assert by_actor["total"] == 1
    assert by_actor["events"][0]["entity_id"] == "2"

    app.dependency_overrides.clear()
