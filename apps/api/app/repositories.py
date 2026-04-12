from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import (
    AuditEvent,
    Blocker,
    CallArtifact,
    DailyRollup,
    Delegation,
    RecurrenceOccurrence,
    RecurrenceTemplate,
    ReviewSession,
    StandardScore,
    SourceChunk,
    SourceDocument,
    Task,
    TaskCandidate,
    TaskUpdate,
    Recommendation,
)


def check_database_connection(db: Session) -> bool:
    try:
        db.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False


def create_task(db: Session, payload: dict) -> Task:
    task = Task(**payload)
    db.add(task)
    db.flush()
    return task


def list_distinct_task_owner_names(db: Session) -> list[str]:
    stmt = select(Task.owner_name).distinct().order_by(Task.owner_name.asc())
    return list(db.scalars(stmt).all())


def list_tasks(
    db: Session,
    status: str | None = None,
    owner_name: str | None = None,
    due_before: datetime | None = None,
    priority: str | None = None,
) -> list[Task]:
    stmt = select(Task)
    if status:
        stmt = stmt.where(Task.status == status)
    if owner_name:
        stmt = stmt.where(Task.owner_name == owner_name)
    if due_before:
        stmt = stmt.where(Task.due_at.is_not(None))
        stmt = stmt.where(Task.due_at <= due_before)
    if priority:
        stmt = stmt.where(Task.priority == priority)
    stmt = stmt.order_by(Task.id.asc())
    return list(db.scalars(stmt).all())


def get_task_by_id(db: Session, task_id: int) -> Task | None:
    return db.get(Task, task_id)


def update_task(db: Session, task: Task, updates: dict) -> Task:
    for key, value in updates.items():
        setattr(task, key, value)
    task.updated_at = datetime.now(timezone.utc)
    db.add(task)
    db.flush()
    return task


def create_audit_event(
    db: Session, entity_type: str, entity_id: str, event_type: str, payload_json: dict
) -> AuditEvent:
    event = AuditEvent(
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        payload_json=payload_json,
    )
    db.add(event)
    db.flush()
    return event


def create_task_update(db: Session, payload: dict) -> TaskUpdate:
    task_update = TaskUpdate(**payload)
    db.add(task_update)
    db.flush()
    return task_update


def list_task_updates(db: Session, task_id: int) -> list[TaskUpdate]:
    stmt = select(TaskUpdate).where(TaskUpdate.task_id == task_id).order_by(TaskUpdate.id.asc())
    return list(db.scalars(stmt).all())


def get_open_blocker_for_task(db: Session, task_id: int) -> Blocker | None:
    stmt = (
        select(Blocker)
        .where(Blocker.task_id == task_id)
        .where(Blocker.closed_at.is_(None))
        .order_by(Blocker.id.desc())
        .limit(1)
    )
    return db.scalar(stmt)


def create_blocker(db: Session, payload: dict) -> Blocker:
    blocker = Blocker(**payload)
    db.add(blocker)
    db.flush()
    return blocker


def create_delegation(db: Session, payload: dict) -> Delegation:
    delegation = Delegation(**payload)
    db.add(delegation)
    db.flush()
    return delegation


def create_recurrence_template(db: Session, payload: dict) -> RecurrenceTemplate:
    template = RecurrenceTemplate(**payload)
    db.add(template)
    db.flush()
    return template


def list_recurrence_templates(db: Session) -> list[RecurrenceTemplate]:
    stmt = select(RecurrenceTemplate).order_by(RecurrenceTemplate.id.asc())
    return list(db.scalars(stmt).all())


def get_recurrence_template_by_id(db: Session, recurrence_template_id: int) -> RecurrenceTemplate | None:
    return db.get(RecurrenceTemplate, recurrence_template_id)


def create_recurrence_occurrence(db: Session, payload: dict) -> RecurrenceOccurrence:
    occurrence = RecurrenceOccurrence(**payload)
    db.add(occurrence)
    db.flush()
    return occurrence


def create_source_document(db: Session, payload: dict) -> SourceDocument:
    source_document = SourceDocument(**payload)
    db.add(source_document)
    db.flush()
    return source_document


def create_source_chunk(db: Session, payload: dict) -> SourceChunk:
    source_chunk = SourceChunk(**payload)
    db.add(source_chunk)
    db.flush()
    return source_chunk


def list_source_documents(db: Session) -> list[SourceDocument]:
    stmt = select(SourceDocument).order_by(SourceDocument.id.asc())
    return list(db.scalars(stmt).all())


def get_source_document_by_id(db: Session, source_document_id: int) -> SourceDocument | None:
    return db.get(SourceDocument, source_document_id)


def list_active_canon_sources(db: Session) -> list[SourceDocument]:
    stmt = (
        select(SourceDocument)
        .where(SourceDocument.source_type == "canon_doc")
        .where(SourceDocument.is_active_canon_version.is_(True))
        .order_by(SourceDocument.canonical_doc_id.asc(), SourceDocument.id.desc())
    )
    return list(db.scalars(stmt).all())


def list_canon_history(db: Session, canonical_doc_id: str) -> list[SourceDocument]:
    stmt = (
        select(SourceDocument)
        .where(SourceDocument.source_type == "canon_doc")
        .where(SourceDocument.canonical_doc_id == canonical_doc_id)
        .order_by(SourceDocument.id.desc())
    )
    return list(db.scalars(stmt).all())


def deactivate_canon_versions(db: Session, canonical_doc_id: str) -> None:
    stmt = (
        select(SourceDocument)
        .where(SourceDocument.source_type == "canon_doc")
        .where(SourceDocument.canonical_doc_id == canonical_doc_id)
        .where(SourceDocument.is_active_canon_version.is_(True))
    )
    existing = list(db.scalars(stmt).all())
    for doc in existing:
        doc.is_active_canon_version = False
        db.add(doc)


def create_task_candidate(db: Session, payload: dict) -> TaskCandidate:
    candidate = TaskCandidate(**payload)
    db.add(candidate)
    db.flush()
    return candidate


def list_task_candidates(db: Session, review_status: str | None = None) -> list[TaskCandidate]:
    stmt = select(TaskCandidate)
    if review_status:
        stmt = stmt.where(TaskCandidate.review_status == review_status)
    stmt = stmt.order_by(TaskCandidate.id.asc())
    return list(db.scalars(stmt).all())


def get_task_candidate_by_id(db: Session, candidate_id: int) -> TaskCandidate | None:
    return db.get(TaskCandidate, candidate_id)


def list_source_chunks_for_source(db: Session, source_document_id: int) -> list[SourceChunk]:
    stmt = (
        select(SourceChunk)
        .where(SourceChunk.source_document_id == source_document_id)
        .order_by(SourceChunk.chunk_index.asc())
    )
    return list(db.scalars(stmt).all())


def list_source_chunks_for_search(
    db: Session,
    *,
    active_canon_only: bool,
    source_types: list[str] | None,
) -> list[tuple[SourceChunk, SourceDocument]]:
    stmt = select(SourceChunk, SourceDocument).join(
        SourceDocument, SourceChunk.source_document_id == SourceDocument.id
    )
    if active_canon_only:
        stmt = stmt.where(SourceDocument.is_active_canon_version.is_(True))
        stmt = stmt.where(SourceDocument.source_type == "canon_doc")
    if source_types:
        stmt = stmt.where(SourceDocument.source_type.in_(source_types))
    rows = db.execute(stmt.order_by(SourceChunk.id.asc())).all()
    return [(row[0], row[1]) for row in rows]


def create_recommendation(db: Session, payload: dict) -> Recommendation:
    recommendation = Recommendation(**payload)
    db.add(recommendation)
    db.flush()
    return recommendation


def list_all_tasks(db: Session) -> list[Task]:
    return list(db.scalars(select(Task).order_by(Task.id.asc())).all())


def list_all_task_updates(db: Session) -> list[TaskUpdate]:
    return list(db.scalars(select(TaskUpdate).order_by(TaskUpdate.id.asc())).all())


def list_open_blockers(db: Session) -> list[Blocker]:
    stmt = (
        select(Blocker)
        .where(Blocker.closed_at.is_(None))
        .order_by(Blocker.opened_at.desc())
    )
    return list(db.scalars(stmt).all())


def list_all_recurrence_occurrences(db: Session) -> list[RecurrenceOccurrence]:
    return list(db.scalars(select(RecurrenceOccurrence).order_by(RecurrenceOccurrence.id.asc())).all())


def list_all_delegations(db: Session) -> list[Delegation]:
    return list(db.scalars(select(Delegation).order_by(Delegation.id.asc())).all())


# ─── Review Sessions ──────────────────────────────────────


def create_review_session(db: Session, payload: dict) -> ReviewSession:
    session = ReviewSession(**payload)
    db.add(session)
    db.flush()
    return session


def list_review_sessions(
    db: Session,
    *,
    task_id: int | None = None,
    owner_name: str | None = None,
    cadence_type: str | None = None,
) -> list[ReviewSession]:
    stmt = select(ReviewSession).order_by(ReviewSession.created_at.desc())
    if task_id is not None:
        stmt = stmt.where(ReviewSession.task_id == task_id)
    if owner_name is not None:
        stmt = stmt.where(ReviewSession.owner_name == owner_name)
    if cadence_type is not None:
        stmt = stmt.where(ReviewSession.cadence_type == cadence_type)
    return list(db.scalars(stmt).all())


def get_review_session_by_id(db: Session, review_id: int) -> ReviewSession | None:
    return db.get(ReviewSession, review_id)


# ─── Standard Scores ─────────────────────────────────────


def create_standard_score(db: Session, payload: dict) -> StandardScore:
    score = StandardScore(**payload)
    db.add(score)
    db.flush()
    return score


def list_standard_scores(
    db: Session,
    *,
    scope_type: str | None = None,
    scope_id: str | None = None,
    metric_type: str | None = None,
    period: str | None = None,
) -> list[StandardScore]:
    stmt = select(StandardScore).order_by(StandardScore.metric_type, StandardScore.metric_name)
    if scope_type is not None:
        stmt = stmt.where(StandardScore.scope_type == scope_type)
    if scope_id is not None:
        stmt = stmt.where(StandardScore.scope_id == scope_id)
    if metric_type is not None:
        stmt = stmt.where(StandardScore.metric_type == metric_type)
    if period is not None:
        stmt = stmt.where(StandardScore.period == period)
    return list(db.scalars(stmt).all())


def list_all_recommendations(db: Session) -> list[Recommendation]:
    return list(db.scalars(select(Recommendation).order_by(Recommendation.id.asc())).all())


def create_daily_rollup(
    db: Session,
    *,
    summary_json: dict,
    preview_text: str,
    generated_at: datetime,
) -> DailyRollup:
    row = DailyRollup(summary_json=summary_json, preview_text=preview_text, generated_at=generated_at)
    db.add(row)
    db.flush()
    return row


def create_call_artifact(db: Session, payload: dict) -> CallArtifact:
    row = CallArtifact(**payload)
    db.add(row)
    db.flush()
    return row


def get_call_artifact_by_id(db: Session, call_artifact_id: int) -> CallArtifact | None:
    return db.get(CallArtifact, call_artifact_id)


def list_call_artifacts(db: Session) -> list[CallArtifact]:
    return list(db.scalars(select(CallArtifact).order_by(CallArtifact.id.asc())).all())
