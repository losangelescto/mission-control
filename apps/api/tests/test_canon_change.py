"""Tests for canon-change detection + the canon-changes routes."""
from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import db as db_module
from app.config import get_settings
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
from app.services.canon_change import detect_canon_change


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


def _seed_active_task(db: Session, *, title: str, description: str = "") -> Task:
    task = Task(
        title=title,
        description=description,
        objective="o",
        standard="s",
        status="in_progress",
        priority="medium",
        owner_name="Alex",
        assigner_name="Manager",
        due_at=None,
        source_confidence=None,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _seed_canon_versions(db: Session, *, doc_id: str) -> tuple[SourceDocument, SourceDocument]:
    prev = SourceDocument(
        filename="canon_v1.txt",
        source_type="canon_doc",
        canonical_doc_id=doc_id,
        version_label="v1",
        is_active_canon_version=False,
        extracted_text="Original wording for vendor onboarding.",
        source_path="inline:canon_v1.txt",
    )
    new = SourceDocument(
        filename="canon_v2.txt",
        source_type="canon_doc",
        canonical_doc_id=doc_id,
        version_label="v2",
        is_active_canon_version=True,
        extracted_text="Revised wording for vendor onboarding with stricter timelines.",
        source_path="inline:canon_v2.txt",
    )
    db.add_all([prev, new])
    db.commit()
    db.refresh(prev)
    db.refresh(new)
    return prev, new


def test_change_summary_prompt_includes_both_versions_and_explicit_length_headers() -> None:
    """Pin the new prompt structure (postfix7 round 2):
    - Both v1 and v2 full bodies present, in triple-quoted blocks
    - Each body preceded by an explicit character-count header
    - The "VERSION 2 IS NON-EMPTY" assertion appears when v2 has content
    - The unified diff is intentionally NOT included
    - System prompt carries the deletion-language guard
    """
    from app.canon_context import (
        build_canon_change_system_prompt,
        build_canon_change_user_message,
    )

    v1 = "Vendors must respond within 24 hours."
    v2 = "Vendors must respond within 4 hours during business, 24 outside. Document each interaction with timestamp and outcome."

    system_prompt = build_canon_change_system_prompt(canon_doc_label="vendor-onboarding")
    user_message = build_canon_change_user_message(
        active_task_titles=["Onboard new vendor"],
        previous_text=v1,
        new_text=v2,
    )

    # System-level guard
    assert "MODIFICATION" in system_prompt
    assert '"deleted"' in system_prompt
    assert '"empty"' in system_prompt
    assert "NEVER use the words" in system_prompt

    # Both full bodies present
    assert "VERSION 1 (PREVIOUS)" in user_message
    assert "VERSION 2 (CURRENT)" in user_message
    assert v1 in user_message
    assert v2 in user_message

    # Explicit length headers
    assert f"VERSION 1 (PREVIOUS) contains: {len(v1)} characters" in user_message
    assert f"VERSION 2 (CURRENT) contains: {len(v2)} characters" in user_message

    # Non-empty assertion line
    assert "VERSION 2 IS NON-EMPTY" in user_message
    assert "Do NOT describe it as removed, deleted, empty, or cleared" in user_message

    # Unified diff intentionally absent
    assert "Unified diff" not in user_message
    assert "@@ " not in user_message  # diff hunk marker


def test_change_summary_prompt_marks_v2_empty_when_v2_actually_empty() -> None:
    """When v2 IS empty, the prompt must label it as such so the LLM is
    free to describe the change as a removal."""
    from app.canon_context import build_canon_change_user_message

    v1 = "Original policy."
    user_message = build_canon_change_user_message(
        active_task_titles=[],
        previous_text=v1,
        new_text="",
    )
    assert "VERSION 2 (CURRENT) contains: EMPTY" in user_message
    assert "VERSION 2 IS EMPTY" in user_message
    assert "[empty]" in user_message


def test_change_summary_prompt_truncates_long_v2_inside_quote_block() -> None:
    """Truncation marker must sit INSIDE the triple-quoted block so the
    LLM cannot mistake it for the end of the document."""
    from app.canon_context import _CANON_TEXT_PREVIEW_MAX, build_canon_change_user_message

    long_text = "a" * (_CANON_TEXT_PREVIEW_MAX + 500)
    user_message = build_canon_change_user_message(
        active_task_titles=[],
        previous_text="short",
        new_text=long_text,
    )
    # Length header still reports the FULL char count, not the preview budget
    assert f"contains: {len(long_text)} characters" in user_message
    # Truncation marker is inside the quoted block (between `"""` lines)
    assert "document continues" in user_message
    # The marker explicitly tells the model the full document is in force
    assert "the full document is in force" in user_message


def test_change_summary_post_processing_logs_warning_on_deletion_language(
    monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    """If the LLM still produces "v2 was deleted" despite the prompt, log
    a warning so the regression is observable. The change_event still
    persists — the warning is observability, not a block."""
    import logging

    _, SessionTesting = _setup_full_db()
    db: Session = SessionTesting()
    prev, new = _seed_canon_versions(db, doc_id="warn-test")

    class _DeletionVoiceProvider:
        def analyze_canon_change(self, *, system_prompt, user_message):  # type: ignore[no-untyped-def]
            from app.providers import CanonChangeAnalysis
            return CanonChangeAnalysis(
                change_summary="VERSION 2 was deleted, leaving the operation with no policy.",
                impact_analysis="Operators should re-read.",
                affected_task_titles=[],
            )

    with caplog.at_level(logging.WARNING, logger="app.services.canon_change"):
        from app.services.canon_change import detect_canon_change

        event = detect_canon_change(
            db,
            new_source=new,
            previous_source=prev,
            ai_provider=_DeletionVoiceProvider(),
        )
        db.commit()

    assert event is not None  # event still persists despite the warning
    assert event.change_summary.startswith("VERSION 2 was deleted")

    misleading = [
        r for r in caplog.records
        if r.message == "canon_change_summary_hallucination_detected"
    ]
    assert len(misleading) == 1, "expected exactly one hallucination-detected warning"
    ctx = misleading[0].__dict__.get("context") or {}
    assert ctx.get("matched_phrases"), (
        f"expected matched_phrases in log context; got {ctx}"
    )
    # The phrase "version 2 was deleted" should be one of the matches
    assert any("version 2 was deleted" in p for p in ctx["matched_phrases"])
    db.close()


def test_change_summary_no_warning_when_v2_genuinely_empty(
    monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    """The guardrail must NOT fire when v2 is literally empty — deletion
    language is accurate in that case."""
    import logging

    _, SessionTesting = _setup_full_db()
    db: Session = SessionTesting()

    prev = SourceDocument(
        filename="canon_v1.txt", source_type="canon_doc",
        canonical_doc_id="empty-v2", version_label="v1",
        is_active_canon_version=False,
        extracted_text="Original policy with substantive content.",
        source_path="inline:v1",
    )
    empty_new = SourceDocument(
        filename="canon_v2.txt", source_type="canon_doc",
        canonical_doc_id="empty-v2", version_label="v2",
        is_active_canon_version=True,
        extracted_text="",  # genuinely empty
        source_path="inline:v2",
    )
    db.add_all([prev, empty_new])
    db.commit()
    db.refresh(prev)
    db.refresh(empty_new)

    class _DeletionVoiceProvider:
        def analyze_canon_change(self, *, system_prompt, user_message):  # type: ignore[no-untyped-def]
            from app.providers import CanonChangeAnalysis
            return CanonChangeAnalysis(
                change_summary="VERSION 2 has been deleted/cleared.",
                impact_analysis="The policy no longer exists.",
                affected_task_titles=[],
            )

    with caplog.at_level(logging.WARNING, logger="app.services.canon_change"):
        from app.services.canon_change import detect_canon_change

        detect_canon_change(
            db, new_source=empty_new, previous_source=prev,
            ai_provider=_DeletionVoiceProvider(),
        )
        db.commit()

    misleading = [
        r for r in caplog.records
        if r.message == "canon_change_summary_hallucination_detected"
    ]
    assert len(misleading) == 0, (
        "guardrail fired even though v2 is genuinely empty — false positive"
    )
    db.close()


def test_detect_canon_change_creates_event_and_marks_task() -> None:
    _, SessionTesting = _setup_full_db()
    db: Session = SessionTesting()

    prev, new = _seed_canon_versions(db, doc_id="canon-vendor")
    affected_task = _seed_active_task(
        db,
        title="Onboard new HVAC vendor",
        description="Coordinate paperwork referencing canon-vendor checklist.",
    )

    event = detect_canon_change(db, new_source=new, previous_source=prev)
    db.commit()
    assert event is not None
    assert event.canon_doc_id == "canon-vendor"
    assert event.previous_source_id == prev.id
    assert event.new_source_id == new.id
    # The body-text mention path should pick up the affected task.
    assert affected_task.id in (event.affected_task_ids or [])
    db.refresh(affected_task)
    assert affected_task.canon_update_pending is True
    db.close()


def test_detect_canon_change_returns_none_without_previous() -> None:
    _, SessionTesting = _setup_full_db()
    db: Session = SessionTesting()
    _, new = _seed_canon_versions(db, doc_id="canon-orphan")
    event = detect_canon_change(db, new_source=new, previous_source=None)
    assert event is None
    db.close()


def test_canon_changes_routes_list_get_acknowledge(monkeypatch: pytest.MonkeyPatch) -> None:
    engine, SessionTesting = _setup_full_db()

    def override_get_db() -> Generator[Session, None, None]:
        d = SessionTesting()
        try:
            yield d
        finally:
            d.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(db_module, "SessionLocal", SessionTesting)

    db: Session = SessionTesting()
    prev, new = _seed_canon_versions(db, doc_id="canon-routes")
    affected = _seed_active_task(
        db,
        title="Update vendor checklist",
        description="references canon-routes",
    )
    affected_id = affected.id
    detect_canon_change(db, new_source=new, previous_source=prev)
    db.commit()
    db.close()

    client = TestClient(app)

    listed = client.get("/canon/changes").json()
    assert listed["unreviewed_count"] == 1
    assert len(listed["events"]) == 1
    event_id = listed["events"][0]["id"]

    detail = client.get(f"/canon/changes/{event_id}").json()
    assert detail["canon_doc_id"] == "canon-routes"
    assert detail["new_source_filename"] == "canon_v2.txt"
    assert detail["previous_source_filename"] == "canon_v1.txt"
    titles = [task["title"] for task in detail["affected_tasks"]]
    assert "Update vendor checklist" in titles

    # Task surfaces canon_update_pending in its TaskResponse shape.
    task_resp = client.get(f"/tasks/{affected_id}").json()
    assert task_resp["canon_update_pending"] is True

    ack = client.post(f"/canon/changes/{event_id}/acknowledge").json()
    assert ack["reviewed"] is True

    # After ack, the affected task's pending flag is cleared.
    task_resp_after = client.get(f"/tasks/{affected_id}").json()
    assert task_resp_after["canon_update_pending"] is False

    listed_after = client.get("/canon/changes").json()
    assert listed_after["unreviewed_count"] == 0

    app.dependency_overrides.clear()


def test_acknowledge_404_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
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

    resp = client.post("/canon/changes/9999/acknowledge")
    assert resp.status_code == 404
    app.dependency_overrides.clear()


# ─── Fix 4: regression tests for the activate-canon-source pipeline ──


def _seed_canon_via_repo(db: Session, *, doc_id: str, version: str, text: str, active: bool):
    """Insert a canon source already-flagged active (mirrors the upload form
    path when the user checks 'Activate as the active canon version')."""
    from app.repositories import create_source_document

    src = create_source_document(
        db,
        {
            "filename": f"{doc_id}-{version}.txt",
            "source_type": "canon_doc",
            "canonical_doc_id": doc_id,
            "version_label": version,
            "is_active_canon_version": active,
            "extracted_text": text,
            "source_path": f"inline:{doc_id}-{version}",
        },
    )
    db.commit()
    db.refresh(src)
    return src


def _ingest_canon_upload(
    db: Session,
    *,
    doc_id: str,
    version: str,
    text: str,
    active: bool,
    title: str | None = None,
):
    """Drive ingest_source_upload directly with a tiny .txt payload.

    Mirrors what the POST /sources/upload route does without the FastAPI
    multipart layer — sufficient for the upload-time activation pipeline
    tests because the file_kind helper accepts .txt as a known suffix.
    """
    from app.services import ingest_source_upload

    return ingest_source_upload(
        db,
        filename=f"{doc_id}-{version}.txt",
        source_type="canon_doc",
        file_bytes=text.encode("utf-8"),
        canonical_doc_id=doc_id,
        version_label=version,
        is_active_canon_version=active,
        title=title,
    )


def test_upload_with_is_active_canon_true_runs_activation_pipeline(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Uploading v2 with is_active_canon_version=true should deactivate v1,
    persist a CanonChangeEvent, mark affected tasks pending, and emit
    canon_change_detected — without any explicit POST /canon/activate call.
    """
    _, SessionTesting = _setup_full_db()
    monkeypatch.setattr(db_module, "SessionLocal", SessionTesting)
    settings = get_settings()
    monkeypatch.setattr(settings, "sources_upload_dir", str(tmp_path / "uploads"))
    db: Session = SessionTesting()

    v1 = _ingest_canon_upload(
        db, doc_id="upload-pipeline", version="v1",
        text="Original vendor onboarding policy.", active=True,
    )
    affected = _seed_active_task(
        db,
        title="Vendor onboarding setup",
        description="references upload-pipeline checklist",
    )
    affected_id = affected.id

    v2 = _ingest_canon_upload(
        db, doc_id="upload-pipeline", version="v2",
        text="Updated vendor onboarding policy with stricter timelines.",
        active=True,
    )

    from app.models import AuditEvent, CanonChangeEvent
    from app.repositories import get_source_document_by_id

    # Prior version flag flipped off, new one is active.
    db.refresh(v1)
    db.refresh(v2)
    assert v1.is_active_canon_version is False
    assert v2.is_active_canon_version is True

    # CanonChangeEvent persisted with the right pair.
    events = list(db.scalars(select(CanonChangeEvent)).all())
    assert len(events) == 1
    assert events[0].previous_source_id == v1.id
    assert events[0].new_source_id == v2.id

    # Affected task flag flipped.
    refreshed = get_source_document_by_id(db, affected_id) and db.get(
        type(affected), affected_id
    )
    assert refreshed is not None and refreshed.canon_update_pending is True

    # Audit events for the activation pipeline emitted.
    actions = [
        e.action
        for e in db.scalars(select(AuditEvent)).all()
        if e.entity_type in ("source", "canon_change")
    ]
    assert "canon_activated" in actions
    assert "canon_change_detected" in actions
    db.close()


def test_upload_with_is_active_canon_false_does_not_trigger_activation(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """If the user uploads but doesn't tick "Activate", no change event."""
    _, SessionTesting = _setup_full_db()
    monkeypatch.setattr(db_module, "SessionLocal", SessionTesting)
    settings = get_settings()
    monkeypatch.setattr(settings, "sources_upload_dir", str(tmp_path / "uploads"))
    db: Session = SessionTesting()

    _ingest_canon_upload(
        db, doc_id="not-activated", version="v1",
        text="Draft vendor policy.", active=False,
    )

    from app.models import AuditEvent, CanonChangeEvent

    events = list(db.scalars(select(CanonChangeEvent)).all())
    assert len(events) == 0
    actions = [e.action for e in db.scalars(select(AuditEvent)).all()]
    assert "canon_activated" not in actions
    db.close()


def test_upload_first_version_with_is_active_emits_canon_activated_with_null_previous(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """First-ever version of a canon doc: no prior to deactivate, no
    change event — but the canon_activated audit must still fire with
    metadata.previous_source_id=None so the trail records the first
    activation moment."""
    _, SessionTesting = _setup_full_db()
    monkeypatch.setattr(db_module, "SessionLocal", SessionTesting)
    settings = get_settings()
    monkeypatch.setattr(settings, "sources_upload_dir", str(tmp_path / "uploads"))
    db: Session = SessionTesting()

    _ingest_canon_upload(
        db, doc_id="first-version", version="v1",
        text="First-ever policy.", active=True,
    )

    from app.models import AuditEvent, CanonChangeEvent

    events = list(db.scalars(select(CanonChangeEvent)).all())
    assert len(events) == 0  # no prior, no change

    activations = [
        e
        for e in db.scalars(select(AuditEvent)).all()
        if e.action == "canon_activated"
    ]
    assert len(activations) == 1
    assert (activations[0].event_metadata or {}).get("previous_source_id") is None
    db.close()


def test_upload_writes_title_into_processing_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _, SessionTesting = _setup_full_db()
    monkeypatch.setattr(db_module, "SessionLocal", SessionTesting)
    settings = get_settings()
    monkeypatch.setattr(settings, "sources_upload_dir", str(tmp_path / "uploads"))
    db: Session = SessionTesting()

    src = _ingest_canon_upload(
        db, doc_id="titled", version="v1",
        text="x", active=False,
        title="Q1 Vendor Onboarding Policy",
    )
    db.refresh(src)
    assert src.processing_metadata == {"title": "Q1 Vendor Onboarding Policy"}
    db.close()


def test_upload_blank_title_leaves_processing_metadata_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _, SessionTesting = _setup_full_db()
    monkeypatch.setattr(db_module, "SessionLocal", SessionTesting)
    settings = get_settings()
    monkeypatch.setattr(settings, "sources_upload_dir", str(tmp_path / "uploads"))
    db: Session = SessionTesting()

    src = _ingest_canon_upload(
        db, doc_id="blank-title", version="v1",
        text="x", active=False,
        title="   ",
    )
    db.refresh(src)
    assert src.processing_metadata is None
    db.close()


def test_v1_then_v2_activation_creates_change_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: register+activate v1, then upload+register+activate v2.
    The second activation must create a canon_change_event row.

    Reproduces the case where v2 was uploaded with is_active_canon_version
    already true — previously the activate hook short-circuited because
    it found the new source as its own 'previous active'."""
    _, SessionTesting = _setup_full_db()
    monkeypatch.setattr(db_module, "SessionLocal", SessionTesting)
    db: Session = SessionTesting()

    from app.services import activate_canon_source, register_canon_source

    v1 = _seed_canon_via_repo(
        db, doc_id="fix4-vendor", version="v1",
        text="Original vendor onboarding policy.", active=False,
    )
    register_canon_source(db, v1.id, "fix4-vendor", "v1")
    activate_canon_source(db, v1.id)

    # v2 uploaded WITH is_active_canon_version=true (the bug-trigger path).
    v2 = _seed_canon_via_repo(
        db, doc_id="fix4-vendor", version="v2",
        text="Updated vendor onboarding policy with stricter timelines.",
        active=True,
    )
    register_canon_source(db, v2.id, "fix4-vendor", "v2")
    activate_canon_source(db, v2.id)

    from app.models import CanonChangeEvent

    events = list(db.scalars(select(CanonChangeEvent)).all())
    assert len(events) == 1, f"expected 1 canon_change_event, got {len(events)}"
    assert events[0].previous_source_id == v1.id
    assert events[0].new_source_id == v2.id
    db.close()


def test_v2_activation_emits_canon_change_audit_event_with_correct_previous_source_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, SessionTesting = _setup_full_db()
    monkeypatch.setattr(db_module, "SessionLocal", SessionTesting)
    db: Session = SessionTesting()

    from app.models import AuditEvent
    from app.services import activate_canon_source, register_canon_source

    v1 = _seed_canon_via_repo(
        db, doc_id="fix4-doc-a", version="v1", text="A1", active=False,
    )
    register_canon_source(db, v1.id, "fix4-doc-a", "v1")
    activate_canon_source(db, v1.id)

    v2 = _seed_canon_via_repo(
        db, doc_id="fix4-doc-a", version="v2", text="A2 changed", active=True,
    )
    register_canon_source(db, v2.id, "fix4-doc-a", "v2")
    activate_canon_source(db, v2.id)

    canon_change_audits = list(
        db.scalars(
            select(AuditEvent).where(AuditEvent.action == "canon_change_detected")
        ).all()
    )
    assert len(canon_change_audits) == 1
    md = canon_change_audits[0].event_metadata or {}
    assert md.get("canon_doc_id") == "fix4-doc-a"
    db.close()


def test_v2_activation_flips_affected_tasks_canon_update_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, SessionTesting = _setup_full_db()
    monkeypatch.setattr(db_module, "SessionLocal", SessionTesting)
    db: Session = SessionTesting()

    from app.services import activate_canon_source, register_canon_source

    v1 = _seed_canon_via_repo(
        db, doc_id="fix4-doc-b", version="v1", text="B1", active=False,
    )
    register_canon_source(db, v1.id, "fix4-doc-b", "v1")
    activate_canon_source(db, v1.id)

    affected = _seed_active_task(
        db,
        title="Update vendor onboarding workflow",
        description="references fix4-doc-b checklist",
    )
    db.refresh(affected)

    v2 = _seed_canon_via_repo(
        db, doc_id="fix4-doc-b", version="v2",
        text="B2 with stricter timelines", active=True,
    )
    register_canon_source(db, v2.id, "fix4-doc-b", "v2")
    activate_canon_source(db, v2.id)

    db.refresh(affected)
    assert affected.canon_update_pending is True
    db.close()


def test_v2_activation_audit_metadata_previous_source_id_is_prior_not_new(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for the audit metadata bug — previous_source_id in the
    canon_activated event must be the prior version's id, not the new one."""
    _, SessionTesting = _setup_full_db()
    monkeypatch.setattr(db_module, "SessionLocal", SessionTesting)
    db: Session = SessionTesting()

    from app.models import AuditEvent
    from app.services import activate_canon_source, register_canon_source

    v1 = _seed_canon_via_repo(
        db, doc_id="fix4-doc-c", version="v1", text="C1", active=False,
    )
    register_canon_source(db, v1.id, "fix4-doc-c", "v1")
    activate_canon_source(db, v1.id)

    v2 = _seed_canon_via_repo(
        db, doc_id="fix4-doc-c", version="v2", text="C2 changed",
        active=True,  # the bug-trigger
    )
    register_canon_source(db, v2.id, "fix4-doc-c", "v2")
    activate_canon_source(db, v2.id)

    activations = list(
        db.scalars(
            select(AuditEvent)
            .where(AuditEvent.action == "canon_activated")
            .where(AuditEvent.entity_id == str(v2.id))
        ).all()
    )
    assert len(activations) == 1
    md = activations[0].event_metadata or {}
    assert md.get("previous_source_id") == v1.id, (
        f"previous_source_id should be v1 ({v1.id}), got {md.get('previous_source_id')}"
    )
    assert md.get("previous_source_id") != v2.id
    db.close()
