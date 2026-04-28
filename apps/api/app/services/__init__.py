from datetime import UTC, datetime, timedelta
from pathlib import Path
import math
import time
from collections import defaultdict
import logging
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.daily_rollup import build_daily_rollup_sections, format_daily_rollup_preview_text
from app.call_action_extraction import extract_call_actions_heuristics
from app.config import get_settings
from app.mail_email_extraction import (
    extract_task_candidates_from_email_text,
    extract_thread_refresh_suggestions,
)
from app.mailbox.repository import get_mailbox_source
from app.models import (
    Blocker,
    CallArtifact,
    DailyRollup,
    Delegation,
    MailboxMessage,
    MailboxThread,
    Obstacle,
    RecurrenceTemplate,
    Recommendation,
    SourceDocument,
    SubTask,
    Task,
    TaskCandidate,
    TaskUpdate,
)
from app.providers import (
    AIProvider,
    EmbeddingsAdapter,
    MockEmbeddingsAdapter,
    get_ai_provider,
)
from app.repositories import (
    check_database_connection,
    create_blocker,
    create_delegation,
    create_recurrence_occurrence,
    create_recurrence_template as repo_create_recurrence_template,
    create_source_document,
    create_task_candidate as repo_create_task_candidate,
    create_recommendation as repo_create_recommendation,
    create_task_update as repo_create_task_update,
    get_source_document_by_id,
    list_source_documents as repo_list_source_documents,
    list_source_chunks_for_search,
    list_source_chunks_for_source,
    deactivate_canon_versions,
    list_active_canon_sources as repo_list_active_canon_sources,
    list_canon_history as repo_list_canon_history,
    create_audit_event,
    create_call_artifact as repo_create_call_artifact,
    create_daily_rollup,
    create_task as repo_create_task,
    get_open_blocker_for_task,
    get_recurrence_template_by_id,
    get_task_by_id,
    get_call_artifact_by_id,
    get_task_candidate_by_id,
    list_recurrence_templates as repo_list_recurrence_templates,
    list_task_updates as repo_list_task_updates,
    list_call_artifacts as repo_list_call_artifacts,
    list_task_candidates as repo_list_task_candidates,
    list_distinct_task_owner_names,
    list_tasks as repo_list_tasks,
    update_task as repo_update_task,
    list_all_tasks,
    list_all_task_updates,
    list_open_blockers,
    list_all_recurrence_occurrences,
    list_all_delegations,
)
from app.task_candidate_extraction import (
    AIExtractionInterface,
    NullAIExtractor,
    candidate_draft_hints_json,
    extract_task_candidates_with_heuristics,
)

logger = logging.getLogger(__name__)

ARTIFACT_TO_SOURCE_TYPE = {
    "transcript": "transcript",
    "summary_doc": "summary_doc",
    "manual_notes": "manual_notes",
}


class ThreadStateSuggestionApprovalError(Exception):
    """thread_state_suggestion rows must not auto-materialize as tasks."""


def create_mail_source_document(db: Session, *, filename: str, extracted_text: str) -> SourceDocument:
    return create_source_document(
        db,
        {
            "filename": filename,
            "source_type": "mail_message",
            "canonical_doc_id": None,
            "version_label": None,
            "is_active_canon_version": False,
            "extracted_text": extracted_text,
            "source_path": f"inline:{filename}",
        },
    )


def get_readiness(db: Session) -> bool:
    return check_database_connection(db)


def _task_audit_payload(task: Task) -> dict:
    return {
        "title": task.title,
        "description": task.description,
        "objective": task.objective,
        "standard": task.standard,
        "status": task.status,
        "priority": task.priority,
        "owner_name": task.owner_name,
        "assigner_name": task.assigner_name,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "source_confidence": task.source_confidence,
    }


def create_task(db: Session, payload: dict) -> Task:
    if not payload.get("due_at"):
        payload["due_at"] = datetime.now(UTC) + timedelta(days=7)
    task = repo_create_task(db, payload)
    create_audit_event(
        db=db,
        entity_type="task",
        entity_id=str(task.id),
        event_type="task_created",
        payload_json=_task_audit_payload(task),
    )
    db.commit()
    db.refresh(task)
    return task


def list_tasks(
    db: Session,
    status: str | None = None,
    owner_name: str | None = None,
    due_before: datetime | None = None,
    priority: str | None = None,
) -> list[Task]:
    return repo_list_tasks(
        db=db, status=status, owner_name=owner_name, due_before=due_before, priority=priority
    )


TASK_FILTER_STATUSES = ["backlog", "up_next", "in_progress", "blocked", "completed"]
TASK_FILTER_PRIORITIES = ["low", "medium", "high", "critical"]


def get_task_filter_options(db: Session) -> tuple[list[str], list[str], list[str]]:
    """Static status/priority lists plus distinct owner_name values (sorted) for list filters."""
    return (
        list(TASK_FILTER_STATUSES),
        list(TASK_FILTER_PRIORITIES),
        list_distinct_task_owner_names(db),
    )


def get_task(db: Session, task_id: int) -> Task | None:
    return get_task_by_id(db, task_id)


def update_task(db: Session, task_id: int, updates: dict) -> Task | None:
    task = get_task_by_id(db, task_id)
    if task is None:
        return None

    updated = repo_update_task(db, task, updates)
    create_audit_event(
        db=db,
        entity_type="task",
        entity_id=str(updated.id),
        event_type="task_updated",
        payload_json=_task_audit_payload(updated),
    )
    db.commit()
    db.refresh(updated)
    return updated


def create_task_update(db: Session, task_id: int, payload: dict) -> TaskUpdate | None:
    task = get_task_by_id(db, task_id)
    if task is None:
        return None
    update = repo_create_task_update(db, {"task_id": task_id, **payload})
    db.commit()
    db.refresh(update)
    return update


def list_task_updates(db: Session, task_id: int) -> list[TaskUpdate] | None:
    task = get_task_by_id(db, task_id)
    if task is None:
        return None
    return repo_list_task_updates(db, task_id)


def block_task(db: Session, task_id: int, payload: dict) -> Task | None:
    task = get_task_by_id(db, task_id)
    if task is None:
        return None

    blocker = get_open_blocker_for_task(db, task_id)
    if blocker is None:
        blocker = create_blocker(db, {"task_id": task_id, **payload})
    else:
        blocker.blocker_type = payload["blocker_type"]
        blocker.blocker_reason = payload["blocker_reason"]
        blocker.severity = payload["severity"]
        blocker.closed_at = None
        blocker.resolution_notes = None

    updated = repo_update_task(db, task, {"status": "blocked"})
    create_audit_event(
        db=db,
        entity_type="task",
        entity_id=str(task_id),
        event_type="task_blocked",
        payload_json={
            "blocker_id": blocker.id,
            "blocker_type": blocker.blocker_type,
            "severity": blocker.severity,
        },
    )
    db.commit()
    db.refresh(updated)
    return updated


def unblock_task(db: Session, task_id: int, resolution_notes: str, next_status: str | None) -> Task | None:
    task = get_task_by_id(db, task_id)
    if task is None:
        return None

    blocker = get_open_blocker_for_task(db, task_id)
    if blocker is None:
        return None

    blocker.closed_at = datetime.now(UTC)
    blocker.resolution_notes = resolution_notes
    target_status = next_status or "in_progress"

    updated = repo_update_task(db, task, {"status": target_status})
    create_audit_event(
        db=db,
        entity_type="task",
        entity_id=str(task_id),
        event_type="task_unblocked",
        payload_json={
            "blocker_id": blocker.id,
            "resolution_notes": resolution_notes,
            "next_status": target_status,
        },
    )
    db.commit()
    db.refresh(updated)
    return updated


def delegate_task(db: Session, task_id: int, delegated_to: str, delegated_by: str) -> Task | None:
    task = get_task_by_id(db, task_id)
    if task is None:
        return None

    delegated_from = task.owner_name
    create_delegation(
        db,
        {
            "task_id": task_id,
            "delegated_from": delegated_from,
            "delegated_to": delegated_to,
            "delegated_by": delegated_by,
        },
    )

    updated = repo_update_task(db, task, {"owner_name": delegated_to})
    create_audit_event(
        db=db,
        entity_type="task",
        entity_id=str(task_id),
        event_type="task_delegated",
        payload_json={
            "delegated_from": delegated_from,
            "delegated_to": delegated_to,
            "delegated_by": delegated_by,
            "assigner_name": task.assigner_name,
        },
    )
    db.commit()
    db.refresh(updated)
    return updated


def create_recurrence_template(db: Session, payload: dict) -> RecurrenceTemplate:
    template = repo_create_recurrence_template(db, payload)
    db.commit()
    db.refresh(template)
    return template


def list_recurrence_templates(db: Session) -> list[RecurrenceTemplate]:
    return repo_list_recurrence_templates(db)


def spawn_recurrence_template(db: Session, recurrence_template_id: int) -> tuple[Task, int] | None:
    template = get_recurrence_template_by_id(db, recurrence_template_id)
    if template is None:
        return None

    due_at = datetime.now(UTC) + timedelta(days=template.default_due_window_days)
    task = repo_create_task(
        db,
        {
            "title": template.title,
            "description": template.description,
            "objective": template.description,
            "standard": "template_spawned",
            "status": "backlog",
            "priority": "normal",
            "owner_name": template.default_owner_name,
            "assigner_name": template.default_assigner_name,
            "due_at": due_at,
            "source_confidence": None,
        },
    )
    occurrence = create_recurrence_occurrence(
        db,
        {
            "recurrence_template_id": template.id,
            "task_id": task.id,
            "occurrence_date": datetime.now(UTC).date(),
            "status": "spawned",
        },
    )
    create_audit_event(
        db=db,
        entity_type="recurrence_template",
        entity_id=str(template.id),
        event_type="recurrence_spawned",
        payload_json={"task_id": task.id, "occurrence_id": occurrence.id},
    )
    db.commit()
    db.refresh(task)
    return task, occurrence.id


def ingest_source_upload(
    db: Session,
    *,
    filename: str,
    source_type: str,
    file_bytes: bytes,
    canonical_doc_id: str | None,
    version_label: str | None,
    is_active_canon_version: bool,
) -> SourceDocument:
    """Persist the uploaded file and create a queued SourceDocument.

    The actual extraction, chunking, and (for media) transcription happens
    in ``app.services.source_pipeline.process_source``, which the route
    schedules as a FastAPI BackgroundTask after this function returns.
    """
    logger.info(
        "source ingestion queued",
        extra={
            "event": "source_ingestion_queued",
            "context": {"filename": filename, "source_type": source_type},
        },
    )
    settings = get_settings()
    upload_dir = Path(settings.sources_upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_name = f"{uuid4().hex}_{filename}"
    file_path = upload_dir / safe_name

    from app.services.audio_utils import file_kind

    if file_kind(file_path) == "unknown":
        raise ValueError(f"unsupported file type: {file_path.suffix}")

    file_path.write_bytes(file_bytes)

    source_document = create_source_document(
        db,
        {
            "filename": filename,
            "source_type": source_type,
            "canonical_doc_id": canonical_doc_id,
            "version_label": version_label,
            "is_active_canon_version": is_active_canon_version,
            "extracted_text": "",
            "source_path": str(file_path),
            "processing_status": "queued",
        },
    )
    db.commit()
    db.refresh(source_document)
    return source_document


def list_source_documents(db: Session) -> list[SourceDocument]:
    return repo_list_source_documents(db)


def get_source_document(db: Session, source_document_id: int) -> SourceDocument | None:
    return get_source_document_by_id(db, source_document_id)


def register_canon_source(
    db: Session, source_id: int, canonical_doc_id: str, version_label: str
) -> SourceDocument | None:
    source_document = get_source_document_by_id(db, source_id)
    if source_document is None:
        return None
    if source_document.source_type != "canon_doc":
        raise ValueError("source must be canon_doc to register canon metadata")

    source_document.canonical_doc_id = canonical_doc_id
    source_document.version_label = version_label
    db.add(source_document)
    db.commit()
    db.refresh(source_document)
    return source_document


def activate_canon_source(db: Session, source_id: int) -> SourceDocument | None:
    source_document = get_source_document_by_id(db, source_id)
    if source_document is None:
        return None
    if source_document.source_type != "canon_doc":
        raise ValueError("source must be canon_doc to activate")
    if not source_document.canonical_doc_id:
        raise ValueError("canonical_doc_id is required before activation")

    deactivate_canon_versions(db, source_document.canonical_doc_id)
    source_document.is_active_canon_version = True
    db.add(source_document)
    db.commit()
    db.refresh(source_document)
    return source_document


def list_active_canon_sources(db: Session) -> list[SourceDocument]:
    return repo_list_active_canon_sources(db)


def get_canon_history(db: Session, canonical_doc_id: str) -> list[SourceDocument]:
    return repo_list_canon_history(db, canonical_doc_id)


def extract_task_candidates_from_source(
    db: Session,
    source_id: int,
    ai_extractor: AIExtractionInterface | None = None,
) -> list[TaskCandidate] | None:
    source = get_source_document_by_id(db, source_id)
    if source is None:
        return None
    t0 = time.monotonic()
    logger.info(
        "task candidate extraction started",
        extra={"event": "candidate_extraction_started", "context": {"source_id": source_id}},
    )

    extractor = ai_extractor or NullAIExtractor()
    heuristic = extract_task_candidates_with_heuristics(
        source_text=source.extracted_text,
        source_date=source.created_at,
    )
    ai_candidates = extractor.extract_candidates(source.extracted_text)
    all_candidates = [*heuristic, *ai_candidates]

    created: list[TaskCandidate] = []
    for candidate in all_candidates:
        row = repo_create_task_candidate(
            db,
            {
                "source_document_id": source.id,
                "title": candidate.title,
                "description": candidate.description,
                "inferred_owner_name": candidate.inferred_owner_name,
                "inferred_due_at": candidate.inferred_due_at,
                "fallback_due_at": candidate.fallback_due_at,
                "review_status": "pending_review",
                "confidence": candidate.confidence,
                "hints_json": candidate_draft_hints_json(candidate),
                "candidate_kind": "new_task",
            },
        )
        created.append(row)

    db.commit()
    for row in created:
        db.refresh(row)
    logger.info(
        "task candidate extraction completed",
        extra={
            "event": "candidate_extraction_completed",
            "context": {
                "source_id": source_id,
                "candidate_count": len(created),
                "duration_ms": round((time.monotonic() - t0) * 1000, 2),
            },
        },
    )
    return created


def extract_task_candidates_from_mail_message(
    db: Session,
    message_id: int,
    ai_extractor: AIExtractionInterface | None = None,
) -> list[TaskCandidate] | None:
    msg = db.get(MailboxMessage, message_id)
    if msg is None:
        return None
    t0 = time.monotonic()
    logger.info(
        "mail message candidate extraction started",
        extra={
            "event": "mail_candidate_extraction_started",
            "context": {"message_id": message_id},
        },
    )
    thread = db.get(MailboxThread, msg.mailbox_thread_id)
    source_doc = create_mail_source_document(
        db,
        filename=f"mail_message_{msg.id}.txt",
        extracted_text=f"Subject: {msg.subject}\n\n{msg.body_text}",
    )
    drafts = extract_task_candidates_from_email_text(
        subject=msg.subject,
        body=msg.body_text,
        received_at=msg.received_at,
        ai_extractor=ai_extractor,
    )
    created: list[TaskCandidate] = []
    for draft in drafts:
        row = repo_create_task_candidate(
            db,
            {
                "source_document_id": source_doc.id,
                "title": draft.title,
                "description": draft.description,
                "inferred_owner_name": draft.inferred_owner_name,
                "inferred_due_at": draft.inferred_due_at,
                "fallback_due_at": draft.fallback_due_at,
                "review_status": "pending_review",
                "confidence": draft.confidence,
                "hints_json": candidate_draft_hints_json(draft),
                "candidate_kind": "new_task",
                "mailbox_message_id": msg.id,
                "mailbox_thread_id": thread.id if thread else None,
            },
        )
        created.append(row)
    db.commit()
    for row in created:
        db.refresh(row)
    logger.info(
        "mail message candidate extraction completed",
        extra={
            "event": "mail_candidate_extraction_completed",
            "context": {
                "message_id": message_id,
                "candidate_count": len(created),
                "duration_ms": round((time.monotonic() - t0) * 1000, 2),
            },
        },
    )
    return created


def refresh_mail_thread_task_state(
    db: Session,
    *,
    external_thread_id: str,
    mailbox_owner: str,
    folder_name: str | None,
    ai_extractor: AIExtractionInterface | None = None,
) -> tuple[MailboxThread | None, list[TaskCandidate]]:
    t0 = time.monotonic()
    logger.info(
        "mail thread task-state refresh extraction started",
        extra={
            "event": "mail_thread_candidate_extraction_started",
            "context": {
                "external_thread_id": external_thread_id,
                "mailbox_owner": mailbox_owner,
                "folder_name": folder_name or "Inbox",
            },
        },
    )
    resolved_folder = folder_name or "Inbox"
    mbox_source = get_mailbox_source(
        db,
        provider="fixture",
        mailbox_owner=mailbox_owner,
        folder_name=resolved_folder,
    )
    if mbox_source is None:
        logger.info(
            "mail thread task-state refresh skipped: mailbox source not found",
            extra={
                "event": "mail_thread_candidate_extraction_skipped",
                "context": {
                    "reason": "mailbox_source_not_found",
                    "external_thread_id": external_thread_id,
                    "mailbox_owner": mailbox_owner,
                },
            },
        )
        return None, []
    thread = db.scalar(
        select(MailboxThread).where(
            MailboxThread.mailbox_source_id == mbox_source.id,
            MailboxThread.external_thread_id == external_thread_id,
        )
    )
    if thread is None:
        logger.info(
            "mail thread task-state refresh skipped: thread not found",
            extra={
                "event": "mail_thread_candidate_extraction_skipped",
                "context": {
                    "reason": "thread_not_found",
                    "external_thread_id": external_thread_id,
                    "mailbox_source_id": mbox_source.id,
                },
            },
        )
        return None, []
    stmt = (
        select(MailboxMessage)
        .where(MailboxMessage.mailbox_thread_id == thread.id)
        .order_by(MailboxMessage.id.asc())
    )
    messages = list(db.scalars(stmt).all())
    last_id = thread.last_refresh_up_to_message_id
    if last_id is None:
        new_msgs = messages
    else:
        new_msgs = [m for m in messages if m.id > last_id]
    if not new_msgs:
        logger.info(
            "mail thread task-state refresh completed: no new messages",
            extra={
                "event": "mail_thread_candidate_extraction_completed",
                "context": {
                    "mailbox_thread_id": thread.id,
                    "candidate_count": 0,
                    "new_message_count": 0,
                    "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                },
            },
        )
        return thread, []
    bodies = [f"Subject: {m.subject}\n{m.body_text}" for m in new_msgs]
    latest_received = max(m.received_at for m in new_msgs)
    drafts = extract_thread_refresh_suggestions(
        thread_subject=thread.subject or "",
        new_message_bodies=bodies,
        source_date=latest_received,
        ai_extractor=ai_extractor,
    )
    bundle_doc = create_mail_source_document(
        db,
        filename=f"mail_thread_refresh_{thread.id}.txt",
        extracted_text="\n---\n".join(bodies),
    )
    created: list[TaskCandidate] = []
    for draft in drafts:
        row = repo_create_task_candidate(
            db,
            {
                "source_document_id": bundle_doc.id,
                "title": draft.title,
                "description": draft.description,
                "inferred_owner_name": draft.inferred_owner_name,
                "inferred_due_at": draft.inferred_due_at,
                "fallback_due_at": draft.fallback_due_at,
                "review_status": "pending_review",
                "confidence": draft.confidence,
                "hints_json": candidate_draft_hints_json(draft),
                "candidate_kind": "thread_state_suggestion",
                "mailbox_message_id": new_msgs[-1].id,
                "mailbox_thread_id": thread.id,
                "related_task_id": None,
            },
        )
        created.append(row)
    thread.last_refresh_up_to_message_id = max(m.id for m in new_msgs)
    db.add(thread)
    db.commit()
    for row in created:
        db.refresh(row)
    db.refresh(thread)
    logger.info(
        "mail thread task-state refresh extraction completed",
        extra={
            "event": "mail_thread_candidate_extraction_completed",
            "context": {
                "mailbox_thread_id": thread.id,
                "candidate_count": len(created),
                "new_message_count": len(new_msgs),
                "duration_ms": round((time.monotonic() - t0) * 1000, 2),
            },
        },
    )
    return thread, created


def ingest_call_artifact_upload(
    db: Session,
    *,
    artifact_type: str,
    filename: str,
    file_bytes: bytes,
    title: str | None,
) -> tuple[CallArtifact, int]:
    st = ARTIFACT_TO_SOURCE_TYPE.get(artifact_type)
    if st is None:
        raise ValueError(f"unsupported artifact_type: {artifact_type}")
    logger.info(
        "call artifact ingestion started",
        extra={
            "event": "call_artifact_ingestion_started",
            "context": {"artifact_type": artifact_type, "filename": filename},
        },
    )
    source_document = ingest_source_upload(
        db,
        filename=filename,
        source_type=st,
        file_bytes=file_bytes,
        canonical_doc_id=None,
        version_label=None,
        is_active_canon_version=False,
    )
    ca = repo_create_call_artifact(
        db,
        {
            "artifact_type": artifact_type,
            "title": title,
            "source_document_id": source_document.id,
        },
    )
    db.commit()
    db.refresh(ca)
    logger.info(
        "call artifact ingestion queued",
        extra={
            "event": "call_artifact_ingestion_queued",
            "context": {
                "call_artifact_id": ca.id,
                "artifact_type": artifact_type,
                "source_document_id": source_document.id,
            },
        },
    )
    return ca, source_document.id


def get_call_artifact(db: Session, call_artifact_id: int) -> CallArtifact | None:
    return get_call_artifact_by_id(db, call_artifact_id)


def list_call_artifacts(db: Session) -> list[CallArtifact]:
    return repo_list_call_artifacts(db)


def extract_actions_from_call_artifact(
    db: Session,
    call_artifact_id: int,
    ai_extractor: AIExtractionInterface | None = None,
) -> list[TaskCandidate] | None:
    t0 = time.monotonic()
    logger.info(
        "call artifact action extraction started",
        extra={
            "event": "call_artifact_extraction_started",
            "context": {"call_artifact_id": call_artifact_id},
        },
    )
    ca = get_call_artifact_by_id(db, call_artifact_id)
    if ca is None:
        return None
    source = get_source_document_by_id(db, ca.source_document_id)
    if source is None:
        return None
    extractor = ai_extractor or NullAIExtractor()
    heuristic = extract_call_actions_heuristics(
        source_text=source.extracted_text,
        source_date=source.created_at,
    )
    ai_extra = extractor.extract_candidates(source.extracted_text)
    all_drafts = [*heuristic, *ai_extra]
    created: list[TaskCandidate] = []
    for draft in all_drafts:
        row = repo_create_task_candidate(
            db,
            {
                "source_document_id": source.id,
                "title": draft.title,
                "description": draft.description,
                "inferred_owner_name": draft.inferred_owner_name,
                "inferred_due_at": draft.inferred_due_at,
                "fallback_due_at": draft.fallback_due_at,
                "review_status": "pending_review",
                "confidence": draft.confidence,
                "hints_json": candidate_draft_hints_json(draft),
                "candidate_kind": "new_task",
                "call_artifact_id": ca.id,
            },
        )
        created.append(row)
    db.commit()
    for row in created:
        db.refresh(row)
    logger.info(
        "call actions extraction completed",
        extra={
            "event": "call_artifact_extraction_completed",
            "context": {
                "call_artifact_id": call_artifact_id,
                "candidate_count": len(created),
                "duration_ms": round((time.monotonic() - t0) * 1000, 2),
            },
        },
    )
    return created


def list_task_candidates(db: Session, review_status: str | None = None) -> list[TaskCandidate]:
    return repo_list_task_candidates(db, review_status=review_status)


def approve_task_candidate(db: Session, candidate_id: int) -> Task | None:
    candidate = get_task_candidate_by_id(db, candidate_id)
    if candidate is None:
        return None
    if candidate.review_status == "approved":
        return None
    if getattr(candidate, "candidate_kind", "new_task") == "thread_state_suggestion":
        raise ThreadStateSuggestionApprovalError()

    due_at = candidate.inferred_due_at or candidate.fallback_due_at or (datetime.now(UTC) + timedelta(days=7))
    priority = "high" if "urgency_hints: none" not in candidate.description.lower() else "medium"
    owner_name = candidate.inferred_owner_name or "unassigned"

    task = repo_create_task(
        db,
        {
            "title": candidate.title,
            "description": f"{candidate.description}\nsource_document_id={candidate.source_document_id}",
            "objective": "Review and execute extracted candidate task",
            "standard": "Candidate reviewed and approved",
            "status": "backlog",
            "priority": priority,
            "owner_name": owner_name,
            "assigner_name": "system",
            "due_at": due_at,
            "source_confidence": candidate.confidence,
        },
    )
    repo_create_task_update(
        db,
        {
            "task_id": task.id,
            "update_type": "candidate_approval",
            "summary": "Task created from reviewed candidate",
            "what_happened": f"Candidate {candidate.id} approved from source {candidate.source_document_id}",
            "options_considered": "approve, reject",
            "steps_taken": "Reviewed extracted fields and approved",
            "next_step": "Start execution planning",
            "created_by": "system",
        },
    )
    candidate.review_status = "approved"
    db.add(candidate)
    create_audit_event(
        db=db,
        entity_type="task_candidate",
        entity_id=str(candidate.id),
        event_type="task_candidate_approved",
        payload_json={"task_id": task.id, "source_document_id": candidate.source_document_id},
    )
    db.commit()
    db.refresh(task)
    return task


def reject_task_candidate(db: Session, candidate_id: int, reason: str | None) -> TaskCandidate | None:
    candidate = get_task_candidate_by_id(db, candidate_id)
    if candidate is None:
        return None
    candidate.review_status = "rejected"
    if reason:
        candidate.description = f"{candidate.description}\nrejection_reason: {reason}"
    db.add(candidate)
    create_audit_event(
        db=db,
        entity_type="task_candidate",
        entity_id=str(candidate.id),
        event_type="task_candidate_rejected",
        payload_json={"reason": reason},
    )
    db.commit()
    db.refresh(candidate)
    return candidate


def dismiss_task_candidate(db: Session, candidate_id: int) -> TaskCandidate | None:
    candidate = get_task_candidate_by_id(db, candidate_id)
    if candidate is None:
        return None
    candidate.review_status = "dismissed"
    db.add(candidate)
    create_audit_event(
        db=db,
        entity_type="task_candidate",
        entity_id=str(candidate.id),
        event_type="task_candidate_dismissed",
        payload_json={},
    )
    db.commit()
    db.refresh(candidate)
    return candidate


def _embedding_to_list(value: object) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [float(v) for v in value]
    if isinstance(value, tuple):
        return [float(v) for v in value]
    if hasattr(value, "tolist"):
        vals = value.tolist()
        return [float(v) for v in vals]
    if isinstance(value, str):
        raw = value.strip()
        if raw.startswith("[") and raw.endswith("]"):
            inner = raw[1:-1].strip()
            if not inner:
                return []
            return [float(part.strip()) for part in inner.split(",")]
    return None


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    size = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(size))
    a_norm = math.sqrt(sum(a[i] * a[i] for i in range(size)))
    b_norm = math.sqrt(sum(b[i] * b[i] for i in range(size)))
    if a_norm == 0 or b_norm == 0:
        return 0.0
    return dot / (a_norm * b_norm)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def embed_source_chunks(
    db: Session,
    source_id: int,
    embeddings_adapter: EmbeddingsAdapter | None = None,
) -> int | None:
    source = get_source_document_by_id(db, source_id)
    if source is None:
        return None

    adapter = embeddings_adapter or MockEmbeddingsAdapter()
    chunks = list_source_chunks_for_source(db, source_id)
    for chunk in chunks:
        chunk.embedding = adapter.embed_text(chunk.chunk_text)
        db.add(chunk)
    db.commit()
    return len(chunks)


def retrieve_search(
    db: Session,
    *,
    query: str,
    active_canon_only: bool,
    source_types: list[str] | None,
    embeddings_adapter: EmbeddingsAdapter | None = None,
    top_k: int = 8,
) -> list[dict]:
    adapter = embeddings_adapter or MockEmbeddingsAdapter()
    qvec = adapter.embed_text(query)

    rows = list_source_chunks_for_search(
        db,
        active_canon_only=active_canon_only,
        source_types=source_types,
    )
    scored: list[dict] = []
    for chunk, source in rows:
        cvec = _embedding_to_list(chunk.embedding)
        if cvec is None:
            continue
        score = _cosine_similarity(qvec, cvec)
        scored.append(
            {
                "source_document_id": source.id,
                "source_filename": source.filename,
                "source_type": source.source_type,
                "canonical_doc_id": source.canonical_doc_id,
                "version_label": source.version_label,
                "is_active_canon_version": source.is_active_canon_version,
                "chunk_index": chunk.chunk_index,
                "chunk_text": chunk.chunk_text,
                "score": score,
            }
        )
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


def _latest_recommendation_for_task(db: Session, task_id: int) -> Recommendation | None:
    stmt = (
        select(Recommendation)
        .where(Recommendation.task_id == task_id)
        .order_by(Recommendation.created_at.desc())
        .limit(1)
    )
    return db.scalar(stmt)


def list_task_recommendations(
    db: Session, *, task_id: int, limit: int = 20
) -> list[Recommendation]:
    # Order by id as tiebreaker — SQLite's second-precision timestamps can
    # collide when multiple recommendations are generated in rapid succession.
    stmt = (
        select(Recommendation)
        .where(Recommendation.task_id == task_id)
        .order_by(Recommendation.created_at.desc(), Recommendation.id.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def _update_to_context_dict(u: TaskUpdate) -> dict:
    return {
        "id": u.id,
        "summary": u.summary,
        "created_by": u.created_by,
        "created_at_display": u.created_at.strftime("%Y-%m-%d") if u.created_at else "",
        "created_at_iso": u.created_at.isoformat() if u.created_at else None,
    }


def _blocker_to_context_dict(b: Blocker | None) -> dict | None:
    if b is None:
        return None
    return {
        "id": b.id,
        "blocker_type": b.blocker_type,
        "blocker_reason": b.blocker_reason,
        "severity": b.severity,
        "opened_at_display": b.opened_at.strftime("%Y-%m-%d") if b.opened_at else "",
        "opened_at_iso": b.opened_at.isoformat() if b.opened_at else None,
    }


def _review_to_context_dict(r) -> dict:  # type: ignore[no-untyped-def]
    return {
        "id": r.id,
        "reviewer": r.reviewer,
        "notes": r.notes,
        "action_items": r.action_items,
        "created_at_display": r.created_at.strftime("%Y-%m-%d") if r.created_at else "",
        "created_at_iso": r.created_at.isoformat() if r.created_at else None,
    }


def _task_history_summary(db: Session, task: Task) -> dict:
    from app.repositories import list_review_sessions as repo_list_review_sessions

    stmt_blockers = select(Blocker).where(Blocker.task_id == task.id)
    all_blockers = list(db.scalars(stmt_blockers).all())
    stmt_delegations = select(Delegation).where(Delegation.task_id == task.id)
    delegations = list(db.scalars(stmt_delegations).all())

    now = datetime.now(UTC)
    days = (now - _as_utc(task.created_at)).days if task.created_at else 0
    return {
        "days_since_creation": days,
        "update_count": len(repo_list_task_updates(db, task.id)),
        "block_count": len(all_blockers),
        "reassignment_count": len(delegations),
        "review_count": len(repo_list_review_sessions(db, task_id=task.id)),
    }


def _task_to_context_dict(task: Task) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "objective": task.objective,
        "standard": task.standard,
        "status": task.status,
        "priority": task.priority,
        "owner_name": task.owner_name,
        "assigner_name": task.assigner_name,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "due_at_display": task.due_at.strftime("%Y-%m-%d") if task.due_at else None,
    }


def _compute_context_hash(
    *,
    task_dict: dict,
    canon_chunks: list[dict],
    updates: list[dict],
    blocker: dict | None,
    reviews: list[dict],
    mode: str,
    subtasks: list[dict] | None = None,
    active_obstacles: list[dict] | None = None,
) -> str:
    """Hex sha256 of the normalised input bundle.

    Only identity-bearing fields are hashed — update IDs, canon chunk IDs,
    review IDs — so text edits to the canon or updates still bust the cache
    via task.updated_at / rec.created_at comparisons elsewhere. The hash is
    deliberately cheap to compute.
    """
    import hashlib as _hashlib
    import json as _json

    bundle = {
        "mode": mode,
        "task": {k: task_dict.get(k) for k in ("id", "status", "priority", "objective", "standard", "owner_name", "due_at")},
        "task_description_len": len(task_dict.get("description") or ""),
        "updates": [{"id": u.get("id"), "ts": u.get("created_at_iso")} for u in updates],
        "blocker": {"id": blocker.get("id")} if blocker else None,
        "reviews": [{"id": r.get("id"), "ts": r.get("created_at_iso")} for r in reviews],
        "canon_chunks": [
            {"sid": c.get("source_document_id"), "ix": c.get("chunk_index")}
            for c in canon_chunks
        ],
        "subtasks": [
            {"id": s.get("id"), "status": s.get("status")} for s in (subtasks or [])
        ],
        "obstacles": [{"id": o.get("id")} for o in (active_obstacles or [])],
    }
    raw = _json.dumps(bundle, sort_keys=True, default=str)
    return _hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_task_recommendation(
    db: Session,
    task_id: int,
    *,
    ai_provider: AIProvider | None = None,
    embeddings_adapter: EmbeddingsAdapter | None = None,
) -> Recommendation | None:
    from app.canon_context import (
        build_standard_system_prompt,
        build_standard_user_message,
        build_unblock_system_prompt,
        build_unblock_user_message,
    )
    from app.repositories import list_review_sessions as repo_list_review_sessions

    task = get_task_by_id(db, task_id)
    if task is None:
        return None
    logger.info(
        "recommendation generation started",
        extra={"event": "recommendation_started", "context": {"task_id": task_id}},
    )

    # ─── Assemble the full context for the prompt + hash ───
    recent_updates_models = repo_list_task_updates(db, task.id)[-10:]
    recent_updates = [_update_to_context_dict(u) for u in reversed(recent_updates_models)]
    blocker_model = get_open_blocker_for_task(db, task.id)
    blocker = _blocker_to_context_dict(blocker_model)
    recent_reviews = [
        _review_to_context_dict(r)
        for r in repo_list_review_sessions(db, task_id=task.id)[:3]
    ]
    history_summary = _task_history_summary(db, task)
    task_dict = _task_to_context_dict(task)

    # Sub-task progress and active obstacles — Phase 2 Day 3 additions.
    # These feed the prompt so the LLM can reason about already-tried work
    # and currently-known blockers instead of repeating itself.
    from app.repositories import (
        list_active_obstacles_for_task,
        list_sub_tasks_for_task,
    )

    subtask_rows = list_sub_tasks_for_task(db, task.id)
    subtask_dicts = [
        {
            "id": s.id,
            "title": s.title,
            "status": s.status,
            "canon_reference": s.canon_reference,
        }
        for s in subtask_rows
    ]
    obstacle_rows = list_active_obstacles_for_task(db, task.id)
    obstacle_dicts = [
        {
            "id": o.id,
            "description": o.description,
            "impact": o.impact,
            "proposed_solutions": o.proposed_solutions or [],
        }
        for o in obstacle_rows
    ]

    # Build a retrieval query from the task + recent update summaries so the
    # canon chunks we pull reflect what has actually happened lately.
    update_text_for_query = "\n".join(f"- {u['summary']}" for u in recent_updates)
    retrieval_query = (
        f"{task.objective}\n{task.standard}\n{task.description}\n{update_text_for_query}"
    )
    canon_context = retrieve_search(
        db,
        query=retrieval_query,
        active_canon_only=True,
        source_types=None,
        embeddings_adapter=embeddings_adapter,
        top_k=5,
    )
    history_context = retrieve_search(
        db,
        query=retrieval_query,
        active_canon_only=False,
        source_types=None,
        embeddings_adapter=embeddings_adapter,
        top_k=5,
    )
    context = canon_context + [
        c for c in history_context if (c["source_document_id"], c["chunk_index"]) not in {
            (x["source_document_id"], x["chunk_index"]) for x in canon_context
        }
    ]

    is_blocked = (task.status == "blocked")
    mode = "unblock" if is_blocked else "standard"
    context_hash = _compute_context_hash(
        task_dict=task_dict,
        canon_chunks=context,
        updates=recent_updates,
        blocker=blocker,
        reviews=recent_reviews,
        mode=mode,
        subtasks=subtask_dicts,
        active_obstacles=obstacle_dicts,
    )

    # ─── Cache: return last rec if fresh AND same input hash ───
    cache_seconds = get_settings().recommendation_cache_seconds
    if cache_seconds > 0:
        latest = _latest_recommendation_for_task(db, task.id)
        if latest is not None and latest.input_context_hash == context_hash:
            age = (datetime.now(UTC) - _as_utc(latest.created_at)).total_seconds()
            if age < cache_seconds:
                logger.info(
                    "recommendation cache hit",
                    extra={
                        "event": "recommendation_cache_hit",
                        "context": {
                            "task_id": task_id,
                            "recommendation_id": latest.id,
                            "age_seconds": round(age, 2),
                            "mode": mode,
                        },
                    },
                )
                return latest

    # ─── Call the provider in the correct mode ───
    provider = ai_provider or get_ai_provider()
    subtask_total = len(subtask_dicts)
    subtask_completed = sum(1 for s in subtask_dicts if s.get("status") == "completed")
    recommendation_context_meta = {
        "canon_chunks_used": len(context),
        "updates_included": len(recent_updates),
        "reviews_included": len(recent_reviews),
        "blocker_active": is_blocked or bool(blocker),
        "subtasks_total": subtask_total,
        "subtasks_completed": subtask_completed,
        "active_obstacles": len(obstacle_dicts),
    }

    if is_blocked:
        unblock_system = build_unblock_system_prompt(
            canon_chunks=context,
            updates=recent_updates,
            blocker=blocker,
            reviews=recent_reviews,
            history_summary=history_summary,
            subtasks=subtask_dicts,
            active_obstacles=obstacle_dicts,
        )
        unblock_user = build_unblock_user_message(task=task_dict)
        unblock = provider.generate_unblock(
            system_prompt=unblock_system,
            user_message=unblock_user,
            context_chunks=context,
        )
        # Synthesise the classic RecommendationDraft fields from the
        # unblock output so existing callers (the POST route, downstream
        # consumers) keep seeing a consistent top-level shape.
        top_alt = unblock.alternatives[0] if unblock.alternatives else {
            "path": "unknown", "first_step": "Clarify the blocker.", "aligned_standard": task.standard,
        }
        synth_objective = f"Unblock: {task.title}".strip() or "Unblock this task"
        synth_standard = top_alt.get("aligned_standard") or task.standard
        synth_plan = unblock.root_cause_analysis
        synth_options = [
            f"{alt.get('path', '?')}: {alt.get('solves', '')}".strip().rstrip(":")
            for alt in unblock.alternatives
        ]
        synth_next = top_alt.get("first_step") or "Clarify the blocker with the assigner."
        response_payload = {
            "blocker_summary": unblock.blocker_summary,
            "root_cause_analysis": unblock.root_cause_analysis,
            "alternatives": unblock.alternatives,
            "recommended_path": unblock.recommended_path,
            "canon_reference": unblock.canon_reference,
            "source_refs": unblock.source_refs,
            "recommendation_context": recommendation_context_meta,
        }
        rec_payload = {
            "task_id": task.id,
            "objective": synth_objective,
            "standard": synth_standard,
            "first_principles_plan": synth_plan,
            "viable_options_json": synth_options,
            "next_action": synth_next,
            "source_refs_json": unblock.source_refs,
            "recommendation_type": "unblock",
            "input_context_hash": context_hash,
            "response_json": response_payload,
        }
    else:
        standard_system = build_standard_system_prompt(
            canon_chunks=context,
            updates=recent_updates,
            blocker=blocker,
            reviews=recent_reviews,
            history_summary=history_summary,
            subtasks=subtask_dicts,
            active_obstacles=obstacle_dicts,
        )
        standard_user = build_standard_user_message(
            task=task_dict,
            objective_seed=task.objective,
            standard_seed=task.standard,
        )
        # Keep the task_description fallback populated for providers that
        # ignore the pre-built prompts (e.g. older mock implementations).
        updates_text = (
            "\n\nRecent updates:\n" + "\n".join(f"- [{u['created_at_display']}] {u['summary']}" for u in recent_updates)
            if recent_updates else ""
        )
        draft = provider.generate_recommendation(
            objective=task.objective,
            standard=task.standard,
            task_description=task.description + updates_text,
            context_chunks=context,
            system_prompt=standard_system,
            user_message=standard_user,
        )
        response_payload = {
            "objective": draft.objective,
            "standard": draft.standard,
            "first_principles_plan": draft.first_principles_plan,
            "viable_options": draft.viable_options,
            "next_action": draft.next_action,
            "source_refs": draft.source_refs,
            "recommendation_context": recommendation_context_meta,
        }
        rec_payload = {
            "task_id": task.id,
            "objective": draft.objective,
            "standard": draft.standard,
            "first_principles_plan": draft.first_principles_plan,
            "viable_options_json": draft.viable_options,
            "next_action": draft.next_action,
            "source_refs_json": draft.source_refs,
            "recommendation_type": "standard",
            "input_context_hash": context_hash,
            "response_json": response_payload,
        }
    recommendation = repo_create_recommendation(db, rec_payload)
    create_audit_event(
        db=db,
        entity_type="task",
        entity_id=str(task.id),
        event_type="recommendation_generated",
        payload_json={
            "recommendation_id": recommendation.id,
            "mode": mode,
        },
    )
    db.commit()
    db.refresh(recommendation)
    logger.info(
        "recommendation generation completed",
        extra={
            "event": "recommendation_completed",
            "context": {
                "task_id": task_id,
                "recommendation_id": recommendation.id,
                "mode": mode,
            },
        },
    )
    return recommendation


def get_daily_review(db: Session) -> dict:
    logger.info("daily review generation started", extra={"event": "daily_review_started"})
    now = datetime.now(UTC)
    tasks = list_all_tasks(db)
    updates = list_all_task_updates(db)
    open_blockers = list_open_blockers(db)
    recurrences = list_all_recurrence_occurrences(db)
    pending_candidates = repo_list_task_candidates(db, review_status="pending_review")

    latest_update_by_task: dict[int, datetime] = {}
    for update in updates:
        current = latest_update_by_task.get(update.task_id)
        if current is None or update.created_at > current:
            latest_update_by_task[update.task_id] = update.created_at

    blocked_task_ids = {blocker.task_id for blocker in open_blockers}

    urgent: list[dict] = []
    blocked: list[dict] = []
    stale: list[dict] = []
    due_soon: list[dict] = []

    for task in tasks:
        if task.status == "completed":
            continue

        ref_time = _as_utc(latest_update_by_task.get(task.id, task.updated_at or task.created_at))
        age_since_update_days = (now - ref_time).days
        due_at = _as_utc(task.due_at) if task.due_at is not None else None
        is_due_soon = due_at is not None and due_at <= now + timedelta(days=2)
        is_urgent = task.priority.lower() in {"high", "urgent", "p0"} or (
            due_at is not None and due_at <= now + timedelta(days=1)
        )

        item = {
            "task_id": task.id,
            "title": task.title,
            "owner_name": task.owner_name,
            "status": task.status,
            "priority": task.priority,
            "due_at": due_at,
        }
        if is_urgent:
            urgent.append({**item, "reason": "high priority or near-term deadline"})
        if task.id in blocked_task_ids or task.status == "blocked":
            blocked.append({**item, "reason": "open blocker or blocked status"})
        if age_since_update_days >= 7:
            stale.append({**item, "reason": f"no recent update for {age_since_update_days} days"})
        if is_due_soon:
            due_soon.append({**item, "reason": "due within 48 hours"})

    recurring_due: list[dict] = []
    for occurrence in recurrences:
        if occurrence.status in {"spawned", "pending"} and occurrence.occurrence_date <= now.date():
            recurring_due.append(
                {
                    "occurrence_id": occurrence.id,
                    "recurrence_template_id": occurrence.recurrence_template_id,
                    "task_id": occurrence.task_id,
                    "occurrence_date": occurrence.occurrence_date.isoformat(),
                    "status": occurrence.status,
                }
            )

    result = {
        "urgent": urgent,
        "blocked": blocked,
        "stale": stale,
        "due_soon": due_soon,
        "recurring_due": recurring_due,
        "candidate_review": pending_candidates,
    }
    logger.info(
        "daily review generation completed",
        extra={
            "event": "daily_review_completed",
            "context": {
                "urgent": len(urgent),
                "blocked": len(blocked),
                "stale": len(stale),
                "due_soon": len(due_soon),
                "recurring_due": len(recurring_due),
                "candidate_review": len(pending_candidates),
            },
        },
    )
    return result


def get_daily_rollup_preview(db: Session) -> dict:
    t0 = time.monotonic()
    logger.info(
        "daily roll-up preview generation started",
        extra={"event": "rollup_generation_started", "context": {"mode": "preview"}},
    )
    summary, _ = build_daily_rollup_sections(db)
    preview_text = format_daily_rollup_preview_text(summary)
    logger.info(
        "daily roll-up preview generation completed",
        extra={
            "event": "rollup_generation_completed",
            "context": {
                "mode": "preview",
                "duration_ms": round((time.monotonic() - t0) * 1000, 2),
            },
        },
    )
    return {"summary": summary, "preview_text": preview_text, "phase": "preview_only"}


def generate_daily_rollup(db: Session) -> DailyRollup:
    settings = get_settings()
    t0 = time.monotonic()
    logger.info(
        "daily roll-up persist generation started",
        extra={"event": "rollup_generation_started", "context": {"mode": "persist"}},
    )
    summary, generated_at = build_daily_rollup_sections(db)
    preview_text = format_daily_rollup_preview_text(summary)
    row = create_daily_rollup(
        db,
        summary_json=summary,
        preview_text=preview_text,
        generated_at=generated_at,
    )
    db.commit()
    db.refresh(row)
    if settings.enable_outbound_rollups:
        logger.info(
            "daily roll-up outbound delivery hook not implemented (ENABLE_OUTBOUND_ROLLUPS is true)",
            extra={
                "event": "rollup_outbound_skipped",
                "context": {"rollup_id": row.id},
            },
        )
    else:
        logger.info(
            "outbound roll-up delivery disabled (ENABLE_OUTBOUND_ROLLUPS=false); record persisted only",
            extra={"event": "rollup_outbound_disabled", "context": {"rollup_id": row.id}},
        )
    logger.info(
        "daily roll-up persist generation completed",
        extra={
            "event": "rollup_generation_completed",
            "context": {
                "mode": "persist",
                "rollup_id": row.id,
                "duration_ms": round((time.monotonic() - t0) * 1000, 2),
            },
        },
    )
    return row


def get_metrics_summary(db: Session) -> dict:
    now = datetime.now(UTC)
    tasks = list_all_tasks(db)
    open_tasks = [task for task in tasks if task.status != "completed"]
    blocked_count = len([task for task in tasks if task.status == "blocked"])
    overdue_count = len(
        [task for task in open_tasks if task.due_at is not None and _as_utc(task.due_at) < now]
    )
    repeat_misses = len(
        [
            task
            for task in open_tasks
            if task.due_at is not None and _as_utc(task.due_at) < now - timedelta(days=7)
        ]
    )
    if open_tasks:
        ages = [(now - _as_utc(task.created_at)).days for task in open_tasks]
        average_task_age_days = round(sum(ages) / len(ages), 2)
    else:
        average_task_age_days = 0.0

    pending_candidates = repo_list_task_candidates(db, review_status="pending_review")
    return {
        "average_task_age_days": average_task_age_days,
        "overdue_count": overdue_count,
        "blocked_count": blocked_count,
        "repeat_misses": repeat_misses,
        "candidate_review_queue_size": len(pending_candidates),
        "total_tasks": len(tasks),
    }


def get_metrics_by_owner(db: Session) -> list[dict]:
    now = datetime.now(UTC)
    tasks = list_all_tasks(db)
    delegations = list_all_delegations(db)
    delegations_by_task: dict[int, list] = defaultdict(list)
    for delegation in delegations:
        delegations_by_task[delegation.task_id].append(delegation)

    by_owner: dict[str, dict] = defaultdict(
        lambda: {
            "owner_name": "",
            "total_tasks": 0,
            "completed_tasks": 0,
            "overdue_tasks": 0,
            "blocked_tasks": 0,
            "delegation_count": 0,
            "delegation_drift_count": 0,
        }
    )

    for task in tasks:
        bucket = by_owner[task.owner_name]
        bucket["owner_name"] = task.owner_name
        bucket["total_tasks"] += 1
        if task.status == "completed":
            bucket["completed_tasks"] += 1
        if task.status == "blocked":
            bucket["blocked_tasks"] += 1
        if task.due_at is not None and task.status != "completed" and _as_utc(task.due_at) < now:
            bucket["overdue_tasks"] += 1

        task_delegations = delegations_by_task.get(task.id, [])
        bucket["delegation_count"] += len(task_delegations)
        for delegation in task_delegations:
            if delegation.delegated_to != task.owner_name:
                bucket["delegation_drift_count"] += 1

    owners: list[dict] = []
    for owner in sorted(by_owner.keys()):
        bucket = by_owner[owner]
        total = bucket["total_tasks"]
        completion_rate = (bucket["completed_tasks"] / total) if total else 0.0
        owners.append(
            {
                **bucket,
                "completion_rate": round(completion_rate, 4),
            }
        )
    return owners


# ─── Sub-tasks ──────────────────────────────────────────────────────────


def create_sub_task_for_task(db: Session, task_id: int, payload: dict) -> SubTask | None:
    task = get_task_by_id(db, task_id)
    if task is None:
        return None
    from app.repositories import create_sub_task, next_sub_task_order

    ordering = payload.get("order")
    if ordering is None:
        ordering = next_sub_task_order(db, task_id)
    row = create_sub_task(
        db,
        {
            "parent_task_id": task_id,
            "title": payload["title"],
            "description": payload.get("description", "") or "",
            "status": payload.get("status", "pending") or "pending",
            "order": ordering,
            "canon_reference": payload.get("canon_reference", "") or "",
        },
    )
    db.commit()
    db.refresh(row)
    return row


def list_sub_tasks(db: Session, task_id: int) -> list[SubTask] | None:
    from app.repositories import list_sub_tasks_for_task

    task = get_task_by_id(db, task_id)
    if task is None:
        return None
    return list_sub_tasks_for_task(db, task_id)


def update_sub_task_by_id(db: Session, sub_task_id: int, updates: dict) -> SubTask | None:
    from app.repositories import get_sub_task_by_id, update_sub_task

    sub_task = get_sub_task_by_id(db, sub_task_id)
    if sub_task is None:
        return None
    scrubbed = {k: v for k, v in updates.items() if v is not None}
    update_sub_task(db, sub_task, scrubbed)
    db.commit()
    db.refresh(sub_task)
    return sub_task


def delete_sub_task_by_id(db: Session, sub_task_id: int) -> bool:
    from app.repositories import delete_sub_task, get_sub_task_by_id

    sub_task = get_sub_task_by_id(db, sub_task_id)
    if sub_task is None:
        return False
    delete_sub_task(db, sub_task)
    db.commit()
    return True


def generate_sub_tasks_preview(
    db: Session,
    task_id: int,
    *,
    ai_provider: AIProvider | None = None,
    embeddings_adapter: EmbeddingsAdapter | None = None,
) -> list[dict] | None:
    """Return a list of sub-task drafts (NOT persisted) for frontend preview.

    The frontend renders the drafts, lets the user edit/accept, then calls
    the standard POST /tasks/{id}/subtasks endpoint for each accepted one
    (or batches). We deliberately do not persist here so the user stays in
    control of what ends up in the sub-task list.
    """
    from app.canon_context import build_subtask_system_prompt, build_subtask_user_message

    task = get_task_by_id(db, task_id)
    if task is None:
        return None

    canon_chunks = retrieve_search(
        db,
        query=f"{task.objective}\n{task.standard}\n{task.description}",
        active_canon_only=True,
        source_types=None,
        embeddings_adapter=embeddings_adapter,
        top_k=5,
    )
    task_dict = _task_to_context_dict(task)
    system_prompt = build_subtask_system_prompt(canon_chunks)
    user_message = build_subtask_user_message(task=task_dict)

    provider = ai_provider or get_ai_provider()
    drafts = provider.generate_subtasks(
        system_prompt=system_prompt,
        user_message=user_message,
    )
    return [
        {"title": d.title, "description": d.description, "canon_reference": d.canon_reference}
        for d in drafts
    ]


# ─── Obstacles ─────────────────────────────────────────────────────────


def create_obstacle_for_task(db: Session, task_id: int, payload: dict) -> Obstacle | None:
    from app.repositories import create_obstacle

    task = get_task_by_id(db, task_id)
    if task is None:
        return None
    proposed = payload.get("proposed_solutions") or []
    # Normalise pydantic models → dicts if they leaked through.
    normalised_solutions = [
        s.model_dump() if hasattr(s, "model_dump") else dict(s)
        for s in proposed
    ]
    row = create_obstacle(
        db,
        {
            "task_id": task_id,
            "description": payload["description"],
            "impact": payload.get("impact", "") or "",
            "status": "active",
            "proposed_solutions": normalised_solutions,
            "resolution_notes": "",
            "identified_by": payload.get("identified_by", "user") or "user",
        },
    )
    db.commit()
    db.refresh(row)
    return row


def list_obstacles(db: Session, task_id: int) -> list[Obstacle] | None:
    from app.repositories import list_obstacles_for_task

    task = get_task_by_id(db, task_id)
    if task is None:
        return None
    return list_obstacles_for_task(db, task_id)


def update_obstacle_by_id(db: Session, obstacle_id: int, updates: dict) -> Obstacle | None:
    from app.repositories import get_obstacle_by_id, update_obstacle

    obstacle = get_obstacle_by_id(db, obstacle_id)
    if obstacle is None:
        return None
    scrubbed = {k: v for k, v in updates.items() if v is not None}
    update_obstacle(db, obstacle, scrubbed)
    db.commit()
    db.refresh(obstacle)
    return obstacle


def resolve_obstacle_by_id(
    db: Session, obstacle_id: int, resolution_notes: str
) -> Obstacle | None:
    from app.repositories import get_obstacle_by_id, update_obstacle

    obstacle = get_obstacle_by_id(db, obstacle_id)
    if obstacle is None:
        return None
    update_obstacle(
        db,
        obstacle,
        {
            "status": "resolved",
            "resolution_notes": resolution_notes,
            "resolved_at": datetime.now(UTC),
        },
    )
    db.commit()
    db.refresh(obstacle)
    return obstacle


def analyze_obstacle_by_id(
    db: Session,
    obstacle_id: int,
    *,
    ai_provider: AIProvider | None = None,
    embeddings_adapter: EmbeddingsAdapter | None = None,
) -> Obstacle | None:
    """Run AI analysis on an obstacle and replace its proposed_solutions.

    Uses the same unblock-mode prompt as Day-2 recommendations. The three
    returned alternatives are mapped onto the ObstacleSolution shape and
    stored on the row.
    """
    from app.canon_context import (
        build_obstacle_system_prompt,
        build_obstacle_user_message,
    )
    from app.repositories import get_obstacle_by_id, update_obstacle

    obstacle = get_obstacle_by_id(db, obstacle_id)
    if obstacle is None:
        return None
    task = get_task_by_id(db, obstacle.task_id)
    if task is None:
        return None

    canon_chunks = retrieve_search(
        db,
        query=f"{task.objective}\n{task.standard}\n{obstacle.description}",
        active_canon_only=True,
        source_types=None,
        embeddings_adapter=embeddings_adapter,
        top_k=5,
    )
    task_dict = _task_to_context_dict(task)
    system_prompt = build_obstacle_system_prompt(canon_chunks)
    user_message = build_obstacle_user_message(
        task=task_dict,
        obstacle_description=obstacle.description,
        obstacle_impact=obstacle.impact,
    )

    provider = ai_provider or get_ai_provider()
    unblock = provider.generate_unblock(
        system_prompt=system_prompt,
        user_message=user_message,
        context_chunks=canon_chunks,
    )

    solutions = [
        {
            "solution": alt.get("solves") or alt.get("path", ""),
            "trade_off": alt.get("tradeoff", ""),
            "first_step": alt.get("first_step", ""),
            "aligned_standard": alt.get("aligned_standard", ""),
            "source": "ai_generated",
        }
        for alt in unblock.alternatives
    ]

    update_obstacle(db, obstacle, {"proposed_solutions": solutions})
    db.commit()
    db.refresh(obstacle)
    return obstacle
