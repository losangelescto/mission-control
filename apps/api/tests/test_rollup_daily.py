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
    DailyRollup,
    Delegation,
    RecurrenceOccurrence,
    RecurrenceTemplate,
    Recommendation,
    SourceDocument,
    Task,
    TaskCandidate,
)


def test_daily_rollup_preview_and_generate_persist() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Task.__table__.create(bind=engine)
    Blocker.__table__.create(bind=engine)
    Delegation.__table__.create(bind=engine)
    RecurrenceTemplate.__table__.create(bind=engine)
    RecurrenceOccurrence.__table__.create(bind=engine)
    SourceDocument.__table__.create(bind=engine)
    CallArtifact.__table__.create(bind=engine)
    TaskCandidate.__table__.create(bind=engine)
    Recommendation.__table__.create(bind=engine)
    DailyRollup.__table__.create(bind=engine)

    now = datetime.now(UTC)
    with TestingSessionLocal() as db:
        t_open = Task(
            title="Rollup urgent",
            description="",
            objective="",
            standard="",
            status="in_progress",
            priority="high",
            owner_name="Alex",
            assigner_name="Jordan",
            due_at=now + timedelta(hours=6),
            source_confidence=0.8,
            created_at=now - timedelta(days=2),
            updated_at=now - timedelta(days=1),
        )
        t_stale_del = Task(
            title="Stale delegation holder",
            description="",
            objective="",
            standard="",
            status="in_progress",
            priority="medium",
            owner_name="Sam",
            assigner_name="Jordan",
            due_at=now + timedelta(days=10),
            source_confidence=0.7,
            created_at=now - timedelta(days=20),
            updated_at=now - timedelta(days=3),
        )
        db.add_all([t_open, t_stale_del])
        db.flush()

        db.add(
            Delegation(
                task_id=t_stale_del.id,
                delegated_from="Sam",
                delegated_to="Alex",
                delegated_by="Jordan",
                delegated_at=now - timedelta(days=10),
            )
        )
        db.add(
            Recommendation(
                task_id=t_open.id,
                objective="obj",
                standard="std",
                first_principles_plan="plan",
                viable_options_json=["a"],
                next_action="Ship the fix",
                source_refs_json=[{"source_document_id": 1, "chunk_index": 0}],
            )
        )

        source = SourceDocument(
            filename="cand.txt",
            source_type="note",
            canonical_doc_id=None,
            version_label=None,
            is_active_canon_version=False,
            extracted_text="",
            source_path="/tmp/cand.txt",
            created_at=now,
        )
        db.add(source)
        db.flush()
        db.add(
            TaskCandidate(
                source_document_id=source.id,
                title="Pending cand",
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
        open_id = t_open.id
        stale_del_id = t_stale_del.id

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    prev = client.get("/rollups/daily/preview")
    assert prev.status_code == 200
    body = prev.json()
    assert body["phase"] == "preview_only"
    assert "Internal preview only" in body["preview_text"]
    assert "Urgent" in body["preview_text"]
    assert "Stale delegated" in body["preview_text"]
    assert "Recommendations" in body["preview_text"]
    assert body["summary"]["urgent"]
    assert any(x["task_id"] == open_id for x in body["summary"]["urgent"])
    assert any(x["task_id"] == stale_del_id for x in body["summary"]["stale_delegated"])
    assert body["summary"]["recommendations_attention"]
    assert body["summary"]["candidate_review"]

    gen = client.post("/rollups/daily/generate")
    assert gen.status_code == 201
    gen_body = gen.json()
    assert gen_body["id"] >= 1
    assert gen_body["phase"] == "preview_only"
    assert gen_body["summary"]["as_of"]

    with TestingSessionLocal() as db:
        row = db.get(DailyRollup, gen_body["id"])
        assert row is not None
        assert row.preview_text == gen_body["preview_text"]
        assert row.summary_json["urgent"]

    app.dependency_overrides.clear()
