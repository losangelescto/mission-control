from collections.abc import Generator
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.main import app
from app.models import (
    Blocker,
    CallArtifact,
    Delegation,
    RecurrenceOccurrence,
    RecurrenceTemplate,
    SourceDocument,
    Task,
    TaskCandidate,
    TaskUpdate,
)


def test_daily_review_and_metrics_routes() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Task.__table__.create(bind=engine)
    Blocker.__table__.create(bind=engine)
    TaskUpdate.__table__.create(bind=engine)
    Delegation.__table__.create(bind=engine)
    RecurrenceTemplate.__table__.create(bind=engine)
    RecurrenceOccurrence.__table__.create(bind=engine)
    SourceDocument.__table__.create(bind=engine)
    CallArtifact.__table__.create(bind=engine)
    TaskCandidate.__table__.create(bind=engine)

    now = datetime.now(UTC)
    with TestingSessionLocal() as db:
        t1 = Task(
            title="Urgent due soon",
            description="",
            objective="",
            standard="",
            status="in_progress",
            priority="high",
            owner_name="Alex",
            assigner_name="Jordan",
            due_at=now + timedelta(hours=12),
            source_confidence=0.8,
            created_at=now - timedelta(days=10),
            updated_at=now - timedelta(days=1),
        )
        t2 = Task(
            title="Blocked task",
            description="",
            objective="",
            standard="",
            status="blocked",
            priority="medium",
            owner_name="Taylor",
            assigner_name="Jordan",
            due_at=now + timedelta(days=5),
            source_confidence=0.7,
            created_at=now - timedelta(days=20),
            updated_at=now - timedelta(days=9),
        )
        t3 = Task(
            title="Overdue miss",
            description="",
            objective="",
            standard="",
            status="in_progress",
            priority="low",
            owner_name="Alex",
            assigner_name="Jordan",
            due_at=now - timedelta(days=8),
            source_confidence=0.6,
            created_at=now - timedelta(days=30),
            updated_at=now - timedelta(days=8),
        )
        t4 = Task(
            title="Completed task",
            description="",
            objective="",
            standard="",
            status="completed",
            priority="low",
            owner_name="Alex",
            assigner_name="Jordan",
            due_at=now - timedelta(days=1),
            source_confidence=0.5,
            created_at=now - timedelta(days=4),
            updated_at=now - timedelta(days=1),
        )
        db.add_all([t1, t2, t3, t4])
        db.flush()

        db.add(
            TaskUpdate(
                task_id=t2.id,
                update_type="status",
                summary="old",
                what_happened="",
                options_considered="",
                steps_taken="",
                next_step="",
                created_by="system",
                created_at=now - timedelta(days=10),
            )
        )

        db.add(
            Delegation(
                task_id=t2.id,
                delegated_from="Taylor",
                delegated_to="Sam",
                delegated_by="Jordan",
                delegated_at=now - timedelta(days=2),
            )
        )

        template = RecurrenceTemplate(
            title="Weekly check",
            description="",
            cadence="weekly",
            default_owner_name="Alex",
            default_assigner_name="Jordan",
            default_due_window_days=7,
            is_active=True,
        )
        db.add(template)
        db.flush()
        db.add(
            RecurrenceOccurrence(
                recurrence_template_id=template.id,
                task_id=None,
                occurrence_date=(now - timedelta(days=1)).date(),
                status="spawned",
            )
        )

        source = SourceDocument(
            filename="fixture.txt",
            source_type="note",
            canonical_doc_id=None,
            version_label=None,
            is_active_canon_version=False,
            extracted_text="",
            source_path="/tmp/fixture.txt",
            created_at=now,
        )
        db.add(source)
        db.flush()
        db.add(
            TaskCandidate(
                source_document_id=source.id,
                title="Review candidate",
                description="",
                inferred_owner_name=None,
                inferred_due_at=None,
                fallback_due_at=now + timedelta(days=7),
                review_status="pending_review",
                confidence=0.5,
                created_at=now,
            )
        )
        db.commit()

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    daily = client.get("/review/daily")
    assert daily.status_code == 200
    daily_payload = daily.json()
    assert len(daily_payload["urgent"]) >= 1
    assert any(item["title"] == "Blocked task" for item in daily_payload["blocked"])
    assert any(item["title"] == "Overdue miss" for item in daily_payload["stale"])
    assert any(item["title"] == "Urgent due soon" for item in daily_payload["due_soon"])
    assert len(daily_payload["recurring_due"]) == 1
    assert len(daily_payload["candidate_review"]) == 1

    summary = client.get("/metrics/summary")
    assert summary.status_code == 200
    summary_payload = summary.json()
    assert summary_payload["overdue_count"] >= 1
    assert summary_payload["blocked_count"] >= 1
    assert summary_payload["repeat_misses"] >= 1
    assert summary_payload["candidate_review_queue_size"] == 1
    assert summary_payload["total_tasks"] == 4

    by_owner = client.get("/metrics/by-owner")
    assert by_owner.status_code == 200
    owners = {row["owner_name"]: row for row in by_owner.json()["owners"]}
    assert "Alex" in owners
    assert "Taylor" in owners
    assert owners["Taylor"]["delegation_count"] >= 1
    assert owners["Taylor"]["delegation_drift_count"] >= 1

    app.dependency_overrides.clear()
