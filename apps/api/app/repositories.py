from datetime import datetime, timezone

from sqlalchemy import delete, or_, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import (
    AuditEvent,
    Blocker,
    CallArtifact,
    CanonChangeEvent,
    DailyRollup,
    Delegation,
    Obstacle,
    RecurrenceOccurrence,
    RecurrenceTemplate,
    ReviewSession,
    StandardScore,
    SourceChunk,
    SourceDocument,
    SubTask,
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


def delete_task(db: Session, task_id: int) -> bool:
    """Delete a task and every row that references it.

    Nullable references (TaskCandidate.related_task_id, ReviewSession.task_id,
    RecurrenceOccurrence.task_id) are detached rather than removed so the
    user-facing rows survive (a candidate belongs to its source; a review
    can outlive the task it was about; a recurrence template can re-spawn).

    Past audit_events are intentionally preserved — they are the historical
    record of what happened to the task. The new ``deleted`` audit event
    is emitted by the service layer.
    """
    task = db.get(Task, task_id)
    if task is None:
        return False

    db.execute(
        update(TaskCandidate)
        .where(TaskCandidate.related_task_id == task_id)
        .values(related_task_id=None)
    )
    db.execute(
        update(ReviewSession)
        .where(ReviewSession.task_id == task_id)
        .values(task_id=None)
    )
    db.execute(
        update(RecurrenceOccurrence)
        .where(RecurrenceOccurrence.task_id == task_id)
        .values(task_id=None)
    )

    db.execute(delete(SubTask).where(SubTask.parent_task_id == task_id))
    db.execute(delete(Obstacle).where(Obstacle.task_id == task_id))
    db.execute(delete(Blocker).where(Blocker.task_id == task_id))
    db.execute(delete(Delegation).where(Delegation.task_id == task_id))
    db.execute(delete(Recommendation).where(Recommendation.task_id == task_id))
    db.execute(delete(TaskUpdate).where(TaskUpdate.task_id == task_id))

    db.delete(task)
    db.flush()
    return True


def delete_source(db: Session, source_id: int) -> bool:
    """Delete a source and every row that references it.

    Active-canon protection lives in the service layer, not here — this
    repo helper assumes the caller has already validated.

    MailboxMessage.source_document_id is nullable (a deleted source
    leaves the message; we just clear the link).
    """
    source = db.get(SourceDocument, source_id)
    if source is None:
        return False

    from app.models import MailboxMessage  # avoid top-level cycle in some tests

    db.execute(
        update(MailboxMessage)
        .where(MailboxMessage.source_document_id == source_id)
        .values(source_document_id=None)
    )

    db.execute(
        delete(SourceChunk).where(SourceChunk.source_document_id == source_id)
    )
    db.execute(
        delete(TaskCandidate).where(TaskCandidate.source_document_id == source_id)
    )
    db.execute(
        delete(CallArtifact).where(CallArtifact.source_document_id == source_id)
    )
    db.execute(
        delete(CanonChangeEvent).where(
            or_(
                CanonChangeEvent.previous_source_id == source_id,
                CanonChangeEvent.new_source_id == source_id,
            )
        )
    )

    db.delete(source)
    db.flush()
    return True


# Map legacy event_type strings to the Day-4 canonical action vocabulary
# (single verbs, no entity prefix). The entity_type column already
# carries the entity, so the action column doesn't need to repeat it.
_LEGACY_EVENT_TYPE_TO_ACTION = {
    "task_created": "created",
    "task_updated": "updated",
    "task_blocked": "blocked",
    "task_unblocked": "unblocked",
    "task_delegated": "assigned",
    "recurrence_spawned": "recurrence_spawned",
}


def create_audit_event(
    db: Session,
    entity_type: str,
    entity_id: str,
    event_type: str,
    payload_json: dict,
    *,
    actor: str = "system",
    action: str | None = None,
    changes: dict | None = None,
    event_metadata: dict | None = None,
) -> AuditEvent:
    """Persist an audit row.

    Legacy positional callers (e.g. ``task_created``) still work — the
    canonical ``action`` is derived from ``event_type`` via the legacy
    map. New callers can pass ``action`` explicitly and fill in
    ``actor``, ``changes``, ``event_metadata``.
    """
    canonical_action = action or _LEGACY_EVENT_TYPE_TO_ACTION.get(event_type, event_type)
    event = AuditEvent(
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        payload_json=payload_json,
        action=canonical_action,
        actor=actor,
        changes=changes if changes is not None else payload_json,
        event_metadata=event_metadata,
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


def query_audit_events(
    db: Session,
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    actor: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AuditEvent]:
    stmt = select(AuditEvent)
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditEvent.entity_id == str(entity_id))
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if actor:
        stmt = stmt.where(AuditEvent.actor == actor)
    stmt = stmt.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
    stmt = stmt.limit(limit).offset(offset)
    return list(db.scalars(stmt).all())


def list_audit_events_for_task(
    db: Session, *, task_id: int, limit: int = 200
) -> list[AuditEvent]:
    """Audit history for a task plus its sub-tasks and obstacles.

    The frontend Activity Log on the task detail panel uses this. We
    union by entity_type+entity_id rather than join because the sub-task
    and obstacle ids don't appear on the task row directly — we look
    them up first and pass their ids as additional filters.
    """
    sub_task_ids = list(
        db.scalars(
            select(SubTask.id).where(SubTask.parent_task_id == task_id)
        ).all()
    )
    obstacle_ids = list(
        db.scalars(
            select(Obstacle.id).where(Obstacle.task_id == task_id)
        ).all()
    )
    task_update_ids = list(
        db.scalars(
            select(TaskUpdate.id).where(TaskUpdate.task_id == task_id)
        ).all()
    )

    conditions = [
        (AuditEvent.entity_type == "task") & (AuditEvent.entity_id == str(task_id)),
    ]
    if sub_task_ids:
        conditions.append(
            (AuditEvent.entity_type == "sub_task")
            & (AuditEvent.entity_id.in_([str(i) for i in sub_task_ids]))
        )
    if obstacle_ids:
        conditions.append(
            (AuditEvent.entity_type == "obstacle")
            & (AuditEvent.entity_id.in_([str(i) for i in obstacle_ids]))
        )
    if task_update_ids:
        conditions.append(
            (AuditEvent.entity_type == "task_update")
            & (AuditEvent.entity_id.in_([str(i) for i in task_update_ids]))
        )

    from sqlalchemy import or_

    stmt = (
        select(AuditEvent)
        .where(or_(*conditions))
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


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


def get_active_canon_for_doc_id(
    db: Session,
    canonical_doc_id: str,
    *,
    exclude_source_id: int | None = None,
) -> SourceDocument | None:
    """Return the currently-active source for a canonical_doc_id, if any.

    ``exclude_source_id`` lets the activation hook ask for "the prior
    active version, not the one I'm about to activate" — essential when
    a new version was uploaded with ``is_active_canon_version=true``
    already set, in which case the bare query would return the new
    source itself.
    """
    stmt = (
        select(SourceDocument)
        .where(SourceDocument.source_type == "canon_doc")
        .where(SourceDocument.canonical_doc_id == canonical_doc_id)
        .where(SourceDocument.is_active_canon_version.is_(True))
        .order_by(SourceDocument.id.desc())
    )
    if exclude_source_id is not None:
        stmt = stmt.where(SourceDocument.id != exclude_source_id)
    return db.scalars(stmt).first()


def create_canon_change_event(db: Session, payload: dict) -> CanonChangeEvent:
    event = CanonChangeEvent(**payload)
    db.add(event)
    db.flush()
    return event


def list_canon_change_events(
    db: Session, *, only_unreviewed: bool = False
) -> list[CanonChangeEvent]:
    stmt = select(CanonChangeEvent)
    if only_unreviewed:
        stmt = stmt.where(CanonChangeEvent.reviewed.is_(False))
    stmt = stmt.order_by(CanonChangeEvent.created_at.desc(), CanonChangeEvent.id.desc())
    return list(db.scalars(stmt).all())


def get_canon_change_event_by_id(db: Session, event_id: int) -> CanonChangeEvent | None:
    return db.get(CanonChangeEvent, event_id)


def count_unreviewed_canon_changes(db: Session) -> int:
    stmt = select(CanonChangeEvent).where(CanonChangeEvent.reviewed.is_(False))
    return len(list(db.scalars(stmt).all()))


def list_active_tasks(db: Session) -> list[Task]:
    """Tasks that are not yet completed — used to compute canon impact."""
    stmt = select(Task).where(Task.status != "completed").order_by(Task.id.asc())
    return list(db.scalars(stmt).all())


def mark_tasks_canon_update_pending(db: Session, task_ids: list[int]) -> None:
    if not task_ids:
        return
    stmt = select(Task).where(Task.id.in_(task_ids))
    for task in db.scalars(stmt).all():
        task.canon_update_pending = True
        db.add(task)


def clear_task_canon_update_pending(db: Session, task_ids: list[int]) -> None:
    if not task_ids:
        return
    stmt = select(Task).where(Task.id.in_(task_ids))
    for task in db.scalars(stmt).all():
        task.canon_update_pending = False
        db.add(task)


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


# ─── Sub-tasks ──────────────────────────────────────────────────────────


def create_sub_task(db: Session, payload: dict) -> SubTask:
    sub_task = SubTask(**payload)
    db.add(sub_task)
    db.flush()
    return sub_task


def list_sub_tasks_for_task(db: Session, task_id: int) -> list[SubTask]:
    stmt = (
        select(SubTask)
        .where(SubTask.parent_task_id == task_id)
        .order_by(SubTask.order.asc(), SubTask.id.asc())
    )
    return list(db.scalars(stmt).all())


def get_sub_task_by_id(db: Session, sub_task_id: int) -> SubTask | None:
    return db.get(SubTask, sub_task_id)


def update_sub_task(db: Session, sub_task: SubTask, updates: dict) -> SubTask:
    for key, value in updates.items():
        if hasattr(sub_task, key):
            setattr(sub_task, key, value)
    db.add(sub_task)
    db.flush()
    return sub_task


def delete_sub_task(db: Session, sub_task: SubTask) -> None:
    db.delete(sub_task)
    db.flush()


def next_sub_task_order(db: Session, task_id: int) -> int:
    stmt = (
        select(SubTask.order)
        .where(SubTask.parent_task_id == task_id)
        .order_by(SubTask.order.desc())
        .limit(1)
    )
    current_max = db.scalar(stmt)
    return 0 if current_max is None else current_max + 1


# ─── Obstacles ──────────────────────────────────────────────────────────


def create_obstacle(db: Session, payload: dict) -> Obstacle:
    obstacle = Obstacle(**payload)
    db.add(obstacle)
    db.flush()
    return obstacle


def list_obstacles_for_task(db: Session, task_id: int) -> list[Obstacle]:
    stmt = (
        select(Obstacle)
        .where(Obstacle.task_id == task_id)
        .order_by(Obstacle.identified_at.desc(), Obstacle.id.desc())
    )
    return list(db.scalars(stmt).all())


def list_active_obstacles_for_task(db: Session, task_id: int) -> list[Obstacle]:
    stmt = (
        select(Obstacle)
        .where(Obstacle.task_id == task_id)
        .where(Obstacle.status == "active")
        .order_by(Obstacle.identified_at.desc(), Obstacle.id.desc())
    )
    return list(db.scalars(stmt).all())


def list_recently_resolved_obstacles_for_task(
    db: Session,
    task_id: int,
    *,
    within_days: int = 14,
    limit: int = 3,
) -> list[Obstacle]:
    """Resolved obstacles whose `resolved_at` falls within the recent window.

    Newest first. Used to inject resolution context into recommendation
    prompts so the LLM can build on what just got unstuck rather than
    re-suggesting the same path.
    """
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=within_days)
    stmt = (
        select(Obstacle)
        .where(Obstacle.task_id == task_id)
        .where(Obstacle.status == "resolved")
        .where(Obstacle.resolved_at.is_not(None))
        .where(Obstacle.resolved_at >= cutoff)
        .order_by(Obstacle.resolved_at.desc(), Obstacle.id.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def get_obstacle_by_id(db: Session, obstacle_id: int) -> Obstacle | None:
    return db.get(Obstacle, obstacle_id)


def update_obstacle(db: Session, obstacle: Obstacle, updates: dict) -> Obstacle:
    for key, value in updates.items():
        if hasattr(obstacle, key):
            setattr(obstacle, key, value)
    db.add(obstacle)
    db.flush()
    return obstacle
