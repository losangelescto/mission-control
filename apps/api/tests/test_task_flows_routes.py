from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.main import app
from app.models import (
    AuditEvent,
    Blocker,
    Delegation,
    RecurrenceOccurrence,
    RecurrenceTemplate,
    Task,
    TaskUpdate,
)


def _setup_client() -> tuple[TestClient, sessionmaker]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    Task.__table__.create(bind=engine)
    TaskUpdate.__table__.create(bind=engine)
    Blocker.__table__.create(bind=engine)
    Delegation.__table__.create(bind=engine)
    RecurrenceTemplate.__table__.create(bind=engine)
    RecurrenceOccurrence.__table__.create(bind=engine)
    AuditEvent.__table__.create(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), TestingSessionLocal


def _create_base_task(client: TestClient) -> int:
    response = client.post(
        "/tasks",
        json={
            "title": "Core Task",
            "description": "Task for flow tests",
            "objective": "Test route flows",
            "standard": "Assertions pass",
            "status": "backlog",
            "priority": "high",
            "owner_name": "Alex",
            "assigner_name": "Jordan",
            "due_at": "2026-04-01T00:00:00Z",
            "source_confidence": 0.75,
        },
    )
    assert response.status_code == 201
    return int(response.json()["id"])


def test_task_updates_routes() -> None:
    client, _session_factory = _setup_client()
    task_id = _create_base_task(client)

    create_response = client.post(
        f"/tasks/{task_id}/updates",
        json={
            "update_type": "progress",
            "summary": "Made progress",
            "what_happened": "Finished first pass",
            "options_considered": "Option A and B",
            "steps_taken": "Wrote tests then code",
            "next_step": "Open PR",
            "created_by": "Alex",
        },
    )
    assert create_response.status_code == 201
    assert create_response.json()["task_id"] == task_id
    assert create_response.json()["update_type"] == "progress"

    list_response = client.get(f"/tasks/{task_id}/updates")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["summary"] == "Made progress"

    missing_response = client.get("/tasks/999/updates")
    assert missing_response.status_code == 404

    app.dependency_overrides.clear()


def test_task_updates_route_with_legacy_update_text_column() -> None:
    client, session_factory = _setup_client()

    # Simulate legacy schema where update_text is NOT NULL while model omits it.
    with session_factory() as db:
        db.execute(
            text("ALTER TABLE task_updates ADD COLUMN update_text TEXT NOT NULL DEFAULT ''")
        )
        db.commit()

    task_id = _create_base_task(client)
    response = client.post(
        f"/tasks/{task_id}/updates",
        json={
            "update_type": "progress",
            "summary": "Legacy-compatible insert",
            "what_happened": "Updated table shape includes update_text",
            "options_considered": "Keep compatibility via db default",
            "steps_taken": "Posted structured update payload",
            "next_step": "Continue flow",
            "created_by": "Alex",
        },
    )
    assert response.status_code == 201

    app.dependency_overrides.clear()


def test_block_unblock_and_delegate_routes() -> None:
    client, session_factory = _setup_client()
    task_id = _create_base_task(client)

    block_response = client.post(
        f"/tasks/{task_id}/block",
        json={
            "blocker_type": "dependency",
            "blocker_reason": "Waiting on upstream",
            "severity": "high",
        },
    )
    assert block_response.status_code == 200
    assert block_response.json()["status"] == "blocked"

    unblock_response = client.post(
        f"/tasks/{task_id}/unblock",
        json={"resolution_notes": "Dependency resolved", "next_status": "in_progress"},
    )
    assert unblock_response.status_code == 200
    assert unblock_response.json()["status"] == "in_progress"

    delegate_response = client.post(
        f"/tasks/{task_id}/delegate",
        json={"delegated_to": "Taylor", "delegated_by": "Jordan"},
    )
    assert delegate_response.status_code == 200
    delegated_task = delegate_response.json()
    assert delegated_task["owner_name"] == "Taylor"
    assert delegated_task["assigner_name"] == "Jordan"

    with session_factory() as db:
        delegation = db.scalar(select(Delegation).where(Delegation.task_id == task_id))
        assert delegation is not None
        assert delegation.delegated_from == "Alex"
        assert delegation.delegated_to == "Taylor"

        blocker = db.scalar(select(Blocker).where(Blocker.task_id == task_id))
        assert blocker is not None
        assert blocker.closed_at is not None
        assert blocker.resolution_notes == "Dependency resolved"

        events = list(db.scalars(select(AuditEvent).order_by(AuditEvent.id.asc())).all())
        event_types = [event.event_type for event in events]
        assert "task_blocked" in event_types
        assert "task_unblocked" in event_types
        assert "task_delegated" in event_types

    app.dependency_overrides.clear()


def test_recurrence_template_create_list_and_spawn() -> None:
    client, session_factory = _setup_client()

    create_template_response = client.post(
        "/recurrence-templates",
        json={
            "title": "Weekly review",
            "description": "Run weekly review checklist",
            "cadence": "weekly",
            "default_owner_name": "Alex",
            "default_assigner_name": "Jordan",
            "default_due_window_days": 3,
            "is_active": True,
        },
    )
    assert create_template_response.status_code == 201
    template_id = int(create_template_response.json()["id"])

    list_response = client.get("/recurrence-templates")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["title"] == "Weekly review"

    spawn_response = client.post(f"/recurrence-templates/{template_id}/spawn")
    assert spawn_response.status_code == 200
    payload = spawn_response.json()
    assert payload["recurrence_template_id"] == template_id
    assert payload["task"]["title"] == "Weekly review"
    assert payload["task"]["owner_name"] == "Alex"
    assert payload["task"]["assigner_name"] == "Jordan"
    assert payload["task"]["status"] == "backlog"

    with session_factory() as db:
        occurrence = db.scalar(
            select(RecurrenceOccurrence).where(
                RecurrenceOccurrence.recurrence_template_id == template_id
            )
        )
        assert occurrence is not None
        assert occurrence.task_id == payload["task"]["id"]

    missing_spawn = client.post("/recurrence-templates/999/spawn")
    assert missing_spawn.status_code == 404

    app.dependency_overrides.clear()
