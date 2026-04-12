from collections.abc import Generator
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db import get_db
from app.main import app
from app.models import (
    AuditEvent,
    CallArtifact,
    MailboxMessage,
    MailboxSource,
    MailboxSyncState,
    MailboxThread,
    SourceChunk,
    SourceDocument,
    Task,
    TaskCandidate,
    TaskUpdate,
)


def _mail_client() -> TestClient:
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
    return TestClient(app)


def test_use_fixture_mailbox_false_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_FIXTURE_MAILBOX", "false")
    get_settings.cache_clear()
    try:
        client = _mail_client()
        r = client.post("/mail/sync-fixture", json={"mailbox_owner": "x@example.com"})
        assert r.status_code == 503
        assert "USE_FIXTURE_MAILBOX" in r.json()["detail"]
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def test_enable_teams_call_connector_false_returns_503(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENABLE_TEAMS_CALL_CONNECTOR", "false")
    monkeypatch.setenv("SOURCES_UPLOAD_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    SourceDocument.__table__.create(bind=engine)
    CallArtifact.__table__.create(bind=engine)
    SourceChunk.__table__.create(bind=engine)
    TaskCandidate.__table__.create(bind=engine)
    Task.__table__.create(bind=engine)
    TaskUpdate.__table__.create(bind=engine)
    AuditEvent.__table__.create(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        buf = BytesIO(b"hello")
        r = client.post(
            "/calls/upload-artifact",
            data={"artifact_type": "manual_notes"},
            files={"file": ("x.txt", buf, "text/plain")},
        )
        assert r.status_code == 503
        assert "ENABLE_TEAMS_CALL_CONNECTOR" in r.json()["detail"]
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def test_phase1_feature_flags_env_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_FIXTURE_MAILBOX", "true")
    monkeypatch.setenv("USE_GRAPH_MAILBOX", "true")
    monkeypatch.setenv("ENABLE_LIVE_CANON_SYNC", "false")
    monkeypatch.setenv("ENABLE_TEAMS_CALL_CONNECTOR", "false")
    monkeypatch.setenv("ENABLE_OUTBOUND_ROLLUPS", "true")
    get_settings.cache_clear()
    try:
        s = get_settings()
        assert s.use_fixture_mailbox is True
        assert s.use_graph_mailbox is True
        assert s.enable_live_canon_sync is False
        assert s.enable_teams_call_connector is False
        assert s.enable_outbound_rollups is True
    finally:
        get_settings.cache_clear()
