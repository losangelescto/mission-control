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
from app.chunking import chunk_text
from app.config import get_settings
from app.mail_email_extraction import (
    extract_task_candidates_from_email_text,
    extract_thread_refresh_suggestions,
)
from app.mailbox.repository import get_mailbox_source
from app.models import (
    CallArtifact,
    DailyRollup,
    MailboxMessage,
    MailboxThread,
    RecurrenceTemplate,
    Recommendation,
    SourceDocument,
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
    create_source_chunk,
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
from app.source_extraction import extract_text, extract_pdf_pages_batched
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
) -> tuple[SourceDocument, int]:
    logger.info(
        "source ingestion started",
        extra={
            "event": "source_ingestion_started",
            "context": {"filename": filename, "source_type": source_type},
        },
    )
    settings = get_settings()
    upload_dir = Path(settings.sources_upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_name = f"{uuid4().hex}_{filename}"
    file_path = upload_dir / safe_name
    file_path.write_bytes(file_bytes)

    is_pdf = file_path.suffix.lower() == ".pdf"

    if is_pdf:
        return _ingest_pdf_chunked(
            db,
            file_path=file_path,
            filename=filename,
            source_type=source_type,
            canonical_doc_id=canonical_doc_id,
            version_label=version_label,
            is_active_canon_version=is_active_canon_version,
        )

    extracted_text = extract_text(file_path)
    source_document = create_source_document(
        db,
        {
            "filename": filename,
            "source_type": source_type,
            "canonical_doc_id": canonical_doc_id,
            "version_label": version_label,
            "is_active_canon_version": is_active_canon_version,
            "extracted_text": extracted_text,
            "source_path": str(file_path),
            "processing_status": "complete",
        },
    )

    chunks = chunk_text(extracted_text)
    for idx, chunk in enumerate(chunks):
        create_source_chunk(
            db,
            {
                "source_document_id": source_document.id,
                "chunk_index": idx,
                "chunk_text": chunk,
                "embedding": None,
            },
        )

    db.commit()
    db.refresh(source_document)
    logger.info(
        "source ingestion completed",
        extra={
            "event": "source_ingestion_completed",
            "context": {
                "source_id": source_document.id,
                "filename": filename,
                "source_type": source_type,
                "chunk_count": len(chunks),
            },
        },
    )
    return source_document, len(chunks)


def _ingest_pdf_chunked(
    db: Session,
    *,
    file_path: Path,
    filename: str,
    source_type: str,
    canonical_doc_id: str | None,
    version_label: str | None,
    is_active_canon_version: bool,
) -> tuple[SourceDocument, int]:
    """Process PDFs page-by-page in batches, committing incrementally.

    Creates the source_document record immediately with processing_status='processing',
    then extracts text in batches of pages. If extraction partially fails, successfully
    extracted pages are preserved and status is set to 'partial'.
    """
    # Create the document record first so we have an ID for chunks.
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
            "processing_status": "processing",
        },
    )
    db.commit()
    db.refresh(source_document)

    all_text_parts: list[str] = []
    chunk_count = 0
    status = "complete"

    try:
        for batch_text in extract_pdf_pages_batched(file_path):
            all_text_parts.append(batch_text)

            # Chunk this batch and write to DB incrementally.
            batch_chunks = chunk_text(batch_text)
            for chunk in batch_chunks:
                create_source_chunk(
                    db,
                    {
                        "source_document_id": source_document.id,
                        "chunk_index": chunk_count,
                        "chunk_text": chunk,
                        "embedding": None,
                    },
                )
                chunk_count += 1

            # Commit after each batch so progress is saved.
            db.commit()
            logger.info(
                "PDF batch committed",
                extra={
                    "event": "pdf_batch_committed",
                    "context": {
                        "source_id": source_document.id,
                        "chunks_so_far": chunk_count,
                    },
                },
            )
    except Exception:
        logger.error(
            "PDF extraction partially failed",
            exc_info=True,
            extra={
                "event": "pdf_extraction_partial_failure",
                "context": {
                    "source_id": source_document.id,
                    "chunks_extracted": chunk_count,
                },
            },
        )
        status = "partial" if chunk_count > 0 else "failed"

    # Update the document with the full extracted text and final status.
    full_text = "\n".join(all_text_parts).strip()
    source_document.extracted_text = full_text
    source_document.processing_status = status
    db.add(source_document)
    db.commit()
    db.refresh(source_document)

    logger.info(
        "PDF source ingestion finished",
        extra={
            "event": "source_ingestion_completed",
            "context": {
                "source_id": source_document.id,
                "filename": filename,
                "processing_status": status,
                "chunk_count": chunk_count,
            },
        },
    )
    return source_document, chunk_count


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
    source_document, chunk_count = ingest_source_upload(
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
        "call artifact ingestion completed",
        extra={
            "event": "call_artifact_ingestion_completed",
            "context": {
                "call_artifact_id": ca.id,
                "artifact_type": artifact_type,
                "chunk_count": chunk_count,
            },
        },
    )
    return ca, chunk_count


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


def generate_task_recommendation(
    db: Session,
    task_id: int,
    *,
    ai_provider: AIProvider | None = None,
    embeddings_adapter: EmbeddingsAdapter | None = None,
) -> Recommendation | None:
    task = get_task_by_id(db, task_id)
    if task is None:
        return None
    logger.info(
        "recommendation generation started",
        extra={"event": "recommendation_started", "context": {"task_id": task_id}},
    )

    # Short-circuit if a recent recommendation is still fresh AND the task
    # has not been modified since it was generated. LLM calls are expensive
    # and noisy — a 5-minute cache is enough to deduplicate rapid retries.
    cache_seconds = get_settings().recommendation_cache_seconds
    if cache_seconds > 0:
        latest = _latest_recommendation_for_task(db, task.id)
        if latest is not None:
            age = (datetime.now(UTC) - _as_utc(latest.created_at)).total_seconds()
            task_updated = _as_utc(task.updated_at)
            rec_created = _as_utc(latest.created_at)
            if age < cache_seconds and task_updated <= rec_created:
                logger.info(
                    "recommendation cache hit",
                    extra={
                        "event": "recommendation_cache_hit",
                        "context": {
                            "task_id": task_id,
                            "recommendation_id": latest.id,
                            "age_seconds": round(age, 2),
                        },
                    },
                )
                return latest

    # Include recent task updates in the recommendation context.
    recent_updates = repo_list_task_updates(db, task.id)[-10:]
    updates_text = ""
    if recent_updates:
        lines = [
            f"- [{u.created_at.strftime('%Y-%m-%d')}] {u.summary}"
            for u in recent_updates
        ]
        updates_text = "\n\nRecent updates:\n" + "\n".join(lines)

    task_desc_with_updates = task.description + updates_text

    # Grounding from active canon plus broader source history.
    canon_context = retrieve_search(
        db,
        query=f"{task.objective}\n{task.standard}\n{task_desc_with_updates}",
        active_canon_only=True,
        source_types=None,
        embeddings_adapter=embeddings_adapter,
        top_k=5,
    )
    history_context = retrieve_search(
        db,
        query=f"{task.objective}\n{task.standard}\n{task_desc_with_updates}",
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

    provider = ai_provider or get_ai_provider()
    draft = provider.generate_recommendation(
        objective=task.objective,
        standard=task.standard,
        task_description=task_desc_with_updates,
        context_chunks=context,
    )
    recommendation = repo_create_recommendation(
        db,
        {
            "task_id": task.id,
            "objective": draft.objective,
            "standard": draft.standard,
            "first_principles_plan": draft.first_principles_plan,
            "viable_options_json": draft.viable_options,
            "next_action": draft.next_action,
            "source_refs_json": draft.source_refs,
        },
    )
    create_audit_event(
        db=db,
        entity_type="task",
        entity_id=str(task.id),
        event_type="recommendation_generated",
        payload_json={"recommendation_id": recommendation.id},
    )
    db.commit()
    db.refresh(recommendation)
    logger.info(
        "recommendation generation completed",
        extra={
            "event": "recommendation_completed",
            "context": {"task_id": task_id, "recommendation_id": recommendation.id},
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
