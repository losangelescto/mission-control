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
        assert len(events) == 3
        assert events[0].event_type == "task_created"
        assert events[1].event_type == "task_created"
        assert events[2].event_type == "task_updated"
        assert events[2].entity_type == "task"
        assert events[2].entity_id == "1"

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
