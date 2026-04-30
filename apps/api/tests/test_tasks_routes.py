from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.main import app
from app.models import AuditEvent, Task


def test_task_crud_and_filters() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Task.__table__.create(bind=engine)
    AuditEvent.__table__.create(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    create_payload = {
        "title": "Ship API CRUD",
        "description": "Implement task CRUD routes",
        "objective": "Deliver baseline task management",
        "standard": "All tests pass",
        "status": "backlog",
        "priority": "high",
        "owner_name": "Alex",
        "assigner_name": "Jordan",
        "due_at": "2026-04-01T12:00:00Z",
        "source_confidence": 0.9,
    }
    create_response = client.post("/tasks", json=create_payload)
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["id"] == 1
    assert created["status"] == "backlog"
    assert created["owner_name"] == "Alex"

    second_payload = {
        "title": "Fix blocker",
        "description": "Resolve schema issue",
        "objective": "Keep release on track",
        "standard": "No migration failures",
        "status": "in_progress",
        "priority": "medium",
        "owner_name": "Taylor",
        "assigner_name": "Jordan",
        "due_at": "2026-05-01T10:00:00Z",
        "source_confidence": 0.8,
    }
    second_response = client.post("/tasks", json=second_payload)
    assert second_response.status_code == 201

    list_response = client.get("/tasks")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 2

    filter_opts = client.get("/tasks/filter-options")
    assert filter_opts.status_code == 200
    fo = filter_opts.json()
    assert fo["statuses"] == ["backlog", "up_next", "in_progress", "blocked", "completed"]
    assert fo["priorities"] == ["low", "medium", "high", "critical"]
    assert set(fo["owners"]) == {"Alex", "Taylor"}

    by_status = client.get("/tasks", params={"status": "backlog"})
    assert by_status.status_code == 200
    assert len(by_status.json()) == 1
    assert by_status.json()[0]["title"] == "Ship API CRUD"

    by_owner = client.get("/tasks", params={"owner_name": "Taylor"})
    assert by_owner.status_code == 200
    assert len(by_owner.json()) == 1
    assert by_owner.json()[0]["title"] == "Fix blocker"

    by_priority = client.get("/tasks", params={"priority": "high"})
    assert by_priority.status_code == 200
    assert len(by_priority.json()) == 1
    assert by_priority.json()[0]["title"] == "Ship API CRUD"

    by_due_before = client.get("/tasks", params={"due_before": "2026-04-15T00:00:00Z"})
    assert by_due_before.status_code == 200
    assert len(by_due_before.json()) == 1
    assert by_due_before.json()[0]["title"] == "Ship API CRUD"

    get_response = client.get("/tasks/1")
    assert get_response.status_code == 200
    assert get_response.json()["title"] == "Ship API CRUD"

    patch_response = client.patch("/tasks/1", json={"status": "in_progress", "priority": "urgent"})
    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert patched["status"] == "in_progress"
    assert patched["priority"] == "urgent"

    with TestingSessionLocal() as db:
        events = list(db.scalars(select(AuditEvent).order_by(AuditEvent.id.asc())).all())
        # 2 creates + 1 update + 1 status_changed (the PATCH flips status)
        assert len(events) == 4
        assert events[0].event_type == "task_created"
        assert events[1].event_type == "task_created"
        assert events[2].event_type == "task_updated"
        assert events[2].entity_type == "task"
        assert events[2].entity_id == "1"
        assert events[3].action == "status_changed"
        assert events[3].changes == {"status": {"old": "backlog", "new": "in_progress"}}

    app.dependency_overrides.clear()


def test_task_not_found_returns_404() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Task.__table__.create(bind=engine)
    AuditEvent.__table__.create(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    missing_get = client.get("/tasks/999")
    assert missing_get.status_code == 404
    assert missing_get.json() == {"detail": "task not found"}

    missing_patch = client.patch("/tasks/999", json={"status": "blocked"})
    assert missing_patch.status_code == 404
    assert missing_patch.json() == {"detail": "task not found"}

    app.dependency_overrides.clear()


def _setup_full_task_db():
    """Bootstrap every table the delete cascade touches."""
    from app.models import (
        Blocker, CallArtifact, Delegation, Obstacle, Recommendation,
        ReviewSession, SourceChunk, SourceDocument, SubTask, TaskCandidate,
        TaskUpdate, RecurrenceTemplate, RecurrenceOccurrence,
        CanonChangeEvent,
    )

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionTesting = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    for model in (
        Task, TaskUpdate, AuditEvent, Blocker, Delegation,
        SourceDocument, SourceChunk, CallArtifact, TaskCandidate,
        ReviewSession, Recommendation, SubTask, Obstacle,
        RecurrenceTemplate, RecurrenceOccurrence, CanonChangeEvent,
    ):
        model.__table__.create(bind=engine)
    return engine, SessionTesting


def test_delete_task_cascades_children() -> None:
    """Creating a task with sub-tasks, obstacles, blockers, updates, and a
    recommendation, then DELETE-ing it, leaves no orphan rows behind."""
    from app.models import (
        Blocker, Obstacle, Recommendation, SubTask, TaskUpdate,
    )

    engine, SessionTesting = _setup_full_task_db()

    def override_get_db() -> Generator[Session, None, None]:
        db = SessionTesting()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    create = client.post(
        "/tasks",
        json={
            "title": "Cascade root",
            "description": "Will be deleted",
            "objective": "test cascade",
            "standard": "Accountability",
            "status": "in_progress",
            "priority": "medium",
            "owner_name": "qa",
            "assigner_name": "qa",
        },
    )
    task_id = create.json()["id"]

    # Children populated directly via session — the create routes for
    # each child have their own validation; this keeps the test focused
    # on the delete cascade.
    with SessionTesting() as db:
        db.add(SubTask(parent_task_id=task_id, title="s1"))
        db.add(SubTask(parent_task_id=task_id, title="s2"))
        db.add(Obstacle(task_id=task_id, description="o1"))
        db.add(Blocker(task_id=task_id, blocker_type="dep", blocker_reason="x", severity="low"))
        db.add(TaskUpdate(
            task_id=task_id, update_type="note", summary="s",
            what_happened="w", options_considered="o",
            steps_taken="t", next_step="n", created_by="qa",
        ))
        db.add(Recommendation(
            task_id=task_id, objective="o", standard="s",
            first_principles_plan="p", viable_options_json=["a", "b"],
            next_action="n", source_refs_json=[],
            recommendation_type="standard",
        ))
        db.commit()

    delete_resp = client.delete(f"/tasks/{task_id}")
    assert delete_resp.status_code == 204

    assert client.get(f"/tasks/{task_id}").status_code == 404
    with SessionTesting() as db:
        assert db.execute(select(SubTask).where(SubTask.parent_task_id == task_id)).first() is None
        assert db.execute(select(Obstacle).where(Obstacle.task_id == task_id)).first() is None
        assert db.execute(select(Blocker).where(Blocker.task_id == task_id)).first() is None
        assert db.execute(select(TaskUpdate).where(TaskUpdate.task_id == task_id)).first() is None
        assert db.execute(select(Recommendation).where(Recommendation.task_id == task_id)).first() is None

    app.dependency_overrides.clear()


def test_delete_task_not_found_returns_404() -> None:
    _, SessionTesting = _setup_full_task_db()

    def override_get_db() -> Generator[Session, None, None]:
        db = SessionTesting()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    resp = client.delete("/tasks/9999")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "task not found"}

    app.dependency_overrides.clear()


def test_delete_task_emits_audit_event() -> None:
    _, SessionTesting = _setup_full_task_db()

    def override_get_db() -> Generator[Session, None, None]:
        db = SessionTesting()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    create = client.post(
        "/tasks",
        json={
            "title": "Audit me",
            "description": "",
            "objective": "audit",
            "standard": "Care",
            "status": "backlog",
            "priority": "low",
            "owner_name": "x",
            "assigner_name": "y",
        },
    )
    task_id = create.json()["id"]
    assert client.delete(f"/tasks/{task_id}").status_code == 204

    audit = client.get(f"/audit?entity_type=task&entity_id={task_id}").json()
    actions = [e["action"] for e in audit["events"]]
    assert "deleted" in actions
    deleted_event = next(e for e in audit["events"] if e["action"] == "deleted")
    assert deleted_event["changes"]["task"]["title"] == "Audit me"

    app.dependency_overrides.clear()
