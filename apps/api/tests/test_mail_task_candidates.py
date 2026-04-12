from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.deps import get_mail_extraction_extractor
from app.db import get_db
from app.main import app
from app.models import (
    AuditEvent,
    CallArtifact,
    MailboxMessage,
    MailboxSource,
    MailboxSyncState,
    MailboxThread,
    SourceDocument,
    Task,
    TaskCandidate,
    TaskUpdate,
)
from app.task_candidate_extraction import CandidateDraft


def _setup_client() -> tuple[TestClient, sessionmaker]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    SourceDocument.__table__.create(bind=engine)
    CallArtifact.__table__.create(bind=engine)
    Task.__table__.create(bind=engine)
    TaskUpdate.__table__.create(bind=engine)
    AuditEvent.__table__.create(bind=engine)
    MailboxSource.__table__.create(bind=engine)
    MailboxThread.__table__.create(bind=engine)
    MailboxMessage.__table__.create(bind=engine)
    MailboxSyncState.__table__.create(bind=engine)
    TaskCandidate.__table__.create(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), TestingSessionLocal


@pytest.fixture
def mock_extractor() -> object:
    class MockExtractor:
        def extract_candidates(self, source_text: str) -> list[CandidateDraft]:
            return [
                CandidateDraft(
                    title="AI-added mail task",
                    description="from mock provider",
                    inferred_owner_name=None,
                    inferred_due_at=None,
                    fallback_due_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
                    confidence=0.99,
                )
            ]

    return MockExtractor()


def test_extract_from_mail_message_links_source_and_mailbox(mock_extractor: object) -> None:
    client, _ = _setup_client()
    app.dependency_overrides[get_mail_extraction_extractor] = lambda: mock_extractor

    owner = "owner@example.com"
    t0 = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    sync = client.post(
        "/mail/sync-fixture",
        json={
            "mailbox_owner": owner,
            "messages": [
                {
                    "external_message_id": "e1",
                    "thread_id": "thr-x",
                    "mailbox_owner": owner,
                    "sender": "a@x.com",
                    "recipients_json": [owner],
                    "subject": "Action needed",
                    "body_text": "TODO: Owner: Sam follow up by 2026-04-10 urgent blocked waiting on vendor",
                    "received_at": t0.isoformat(),
                }
            ],
        },
    )
    assert sync.status_code == 200
    listed = client.get("/mail/messages", params={"mailbox_owner": owner})
    mid = listed.json()[0]["id"]

    ext = client.post(f"/mail/messages/{mid}/extract-task-candidates")
    assert ext.status_code == 200
    cands = ext.json()
    assert len(cands) >= 1
    first = cands[0]
    assert first["mailbox_message_id"] == mid
    assert first["candidate_kind"] == "new_task"
    assert "urgency" in first["hints_json"]
    assert first["source_document_id"] is not None

    app.dependency_overrides.pop(get_mail_extraction_extractor, None)


def test_thread_refresh_creates_review_only_suggestions() -> None:
    client, _ = _setup_client()
    owner = "owner@example.com"
    t0 = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    client.post(
        "/mail/sync-fixture",
        json={
            "mailbox_owner": owner,
            "messages": [
                {
                    "external_message_id": "m1",
                    "thread_id": "thr-done",
                    "mailbox_owner": owner,
                    "sender": "a@x.com",
                    "recipients_json": [owner],
                    "subject": "Project",
                    "body_text": "This is completed and resolved.",
                    "received_at": t0.isoformat(),
                },
                {
                    "external_message_id": "m2",
                    "thread_id": "thr-done",
                    "mailbox_owner": owner,
                    "sender": owner,
                    "recipients_json": ["a@x.com"],
                    "subject": "Re: Project",
                    "body_text": "We are blocked waiting on approval. Please follow up next week.",
                    "received_at": t0.isoformat(),
                },
            ],
        },
    )
    r = client.post(
        "/mail/threads/thr-done/refresh-task-state",
        params={"mailbox_owner": owner},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["external_thread_id"] == "thr-done"
    assert len(body["candidates"]) >= 1
    kinds = {c["candidate_kind"] for c in body["candidates"]}
    assert "thread_state_suggestion" in kinds

    cid = body["candidates"][0]["id"]
    approve = client.post(f"/task-candidates/{cid}/approve")
    assert approve.status_code == 400

    r2 = client.post(
        "/mail/threads/thr-done/refresh-task-state",
        params={"mailbox_owner": owner},
    )
    assert r2.status_code == 200
    assert r2.json()["candidates"] == []
