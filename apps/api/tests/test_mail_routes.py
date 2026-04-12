from collections.abc import Generator
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.main import app
from app.models import MailboxMessage, MailboxSource, MailboxSyncState, MailboxThread, SourceDocument


def _setup_client() -> tuple[TestClient, sessionmaker]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    SourceDocument.__table__.create(bind=engine)
    MailboxSource.__table__.create(bind=engine)
    MailboxThread.__table__.create(bind=engine)
    MailboxMessage.__table__.create(bind=engine)
    MailboxSyncState.__table__.create(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), TestingSessionLocal


def test_mail_sync_fixture_and_thread_grouping() -> None:
    client, _ = _setup_client()
    owner = "owner@example.com"
    r = client.post("/mail/sync-fixture", json={"mailbox_owner": owner})
    assert r.status_code == 200
    body = r.json()
    assert body["inserted"] == 3
    assert body["skipped_duplicates"] == 0

    listed = client.get("/mail/messages", params={"mailbox_owner": owner})
    assert listed.status_code == 200
    assert len(listed.json()) == 3

    thread = client.get(
        "/mail/threads/fixture-thread-1",
        params={"mailbox_owner": owner},
    )
    assert thread.status_code == 200
    tj = thread.json()
    assert tj["thread"]["external_thread_id"] == "fixture-thread-1"
    assert tj["thread"]["message_count"] == 2
    assert len(tj["messages"]) == 2

    app.dependency_overrides.clear()


def test_mail_sync_dedupe_second_run() -> None:
    client, _ = _setup_client()
    owner = "owner@example.com"
    first = client.post("/mail/sync-fixture", json={"mailbox_owner": owner})
    assert first.json()["inserted"] == 3
    second = client.post("/mail/sync-fixture", json={"mailbox_owner": owner})
    assert second.status_code == 200
    assert second.json()["inserted"] == 0
    assert second.json()["skipped_duplicates"] == 3

    listed = client.get("/mail/messages", params={"mailbox_owner": owner})
    assert len(listed.json()) == 3

    app.dependency_overrides.clear()


def test_mail_custom_messages_same_thread_grouped() -> None:
    client, _ = _setup_client()
    owner = "custom@example.com"
    t0 = datetime(2026, 2, 1, 10, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 2, 1, 11, 0, 0, tzinfo=timezone.utc)
    payload = {
        "mailbox_owner": owner,
        "folder_name": "Inbox",
        "messages": [
            {
                "external_message_id": "m-1",
                "thread_id": "thr-a",
                "mailbox_owner": owner,
                "sender": "a@x.com",
                "recipients_json": [owner],
                "subject": "S1",
                "body_text": "one",
                "received_at": t0.isoformat(),
            },
            {
                "external_message_id": "m-2",
                "thread_id": "thr-a",
                "mailbox_owner": owner,
                "sender": owner,
                "recipients_json": ["a@x.com"],
                "subject": "Re: S1",
                "body_text": "two",
                "received_at": t1.isoformat(),
            },
        ],
    }
    r = client.post("/mail/sync-fixture", json=payload)
    assert r.status_code == 200
    assert r.json()["inserted"] == 2

    thr = client.get("/mail/threads/thr-a", params={"mailbox_owner": owner})
    assert thr.status_code == 200
    assert thr.json()["thread"]["message_count"] == 2

    app.dependency_overrides.clear()


def test_mail_get_message_by_id() -> None:
    client, _ = _setup_client()
    owner = "owner@example.com"
    client.post("/mail/sync-fixture", json={"mailbox_owner": owner})
    listed = client.get("/mail/messages", params={"mailbox_owner": owner})
    mid = listed.json()[0]["id"]
    one = client.get(f"/mail/messages/{mid}")
    assert one.status_code == 200
    assert one.json()["id"] == mid

    app.dependency_overrides.clear()
