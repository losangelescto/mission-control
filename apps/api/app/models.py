from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db import Base


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    standard: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    priority: Mapped[str] = mapped_column(String(50), nullable=False)
    owner_name: Mapped[str] = mapped_column(String(255), nullable=False)
    assigner_name: Mapped[str] = mapped_column(String(255), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class TaskUpdate(Base):
    __tablename__ = "task_updates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    update_type: Mapped[str] = mapped_column(String(50), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    what_happened: Mapped[str] = mapped_column(Text, nullable=False)
    options_considered: Mapped[str] = mapped_column(Text, nullable=False)
    steps_taken: Mapped[str] = mapped_column(Text, nullable=False)
    next_step: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Blocker(Base):
    __tablename__ = "blockers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    blocker_type: Mapped[str] = mapped_column(String(100), nullable=False)
    blocker_reason: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(50), nullable=False)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Delegation(Base):
    __tablename__ = "delegations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    delegated_from: Mapped[str] = mapped_column(String(255), nullable=False)
    delegated_to: Mapped[str] = mapped_column(String(255), nullable=False)
    delegated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    delegated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RecurrenceTemplate(Base):
    __tablename__ = "recurrence_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    cadence: Mapped[str] = mapped_column(String(100), nullable=False)
    default_owner_name: Mapped[str] = mapped_column(String(255), nullable=False)
    default_assigner_name: Mapped[str] = mapped_column(String(255), nullable=False)
    default_due_window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class RecurrenceOccurrence(Base):
    __tablename__ = "recurrence_occurrences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recurrence_template_id: Mapped[int] = mapped_column(
        ForeignKey("recurrence_templates.id"), nullable=False, index=True
    )
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    occurrence_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    canonical_doc_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active_canon_version: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    processing_status: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="complete"
    )
    pages_processed: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    pages_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CallArtifact(Base):
    """Manual-first call artifact (uploaded file); links to source_documents for chunks + task flow."""

    __tablename__ = "call_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    artifact_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_document_id: Mapped[int] = mapped_column(
        ForeignKey("source_documents.id"), nullable=False, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SourceChunk(Base):
    __tablename__ = "source_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_document_id: Mapped[int] = mapped_column(
        ForeignKey("source_documents.id"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[object | None] = mapped_column(Vector(1536), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TaskCandidate(Base):
    __tablename__ = "task_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_document_id: Mapped[int] = mapped_column(
        ForeignKey("source_documents.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    inferred_owner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    inferred_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fallback_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_status: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    hints_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    candidate_kind: Mapped[str] = mapped_column(
        String(50), nullable=False, default="new_task", server_default="new_task"
    )
    mailbox_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("mailbox_messages.id"), nullable=True, index=True
    )
    mailbox_thread_id: Mapped[int | None] = mapped_column(
        ForeignKey("mailbox_threads.id"), nullable=True, index=True
    )
    related_task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    call_artifact_id: Mapped[int | None] = mapped_column(
        ForeignKey("call_artifacts.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SubTask(Base):
    """A concrete action step that belongs to a parent task.

    Sub-tasks are ordered (see ``order``) and one level deep — we do not
    model sub-sub-tasks. They are independently completable; finishing the
    last sub-task does not auto-complete the parent. ``canon_reference``
    is free-form text so the LLM can write either a Standard name
    ("Consistency") or a longer citation ("Founding Charter §3").
    """

    __tablename__ = "sub_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="pending")
    order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    canon_reference: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Obstacle(Base):
    """A specific thing blocking a task, with proposed solutions.

    Distinct from ``Blocker`` (the Phase-1 open/closed state flag on a task):
    an Obstacle is a richer record of what is in the way, why it matters,
    and concrete first-principles alternatives for moving forward.
    ``proposed_solutions`` is a JSON array of dicts, each shaped like:
    ``{solution, trade_off, first_step, aligned_standard, source}``.
    """

    __tablename__ = "obstacles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    impact: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="active")
    proposed_solutions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    resolution_notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    identified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    identified_by: Mapped[str] = mapped_column(String(255), nullable=False, server_default="system")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    standard: Mapped[str] = mapped_column(Text, nullable=False)
    first_principles_plan: Mapped[str] = mapped_column(Text, nullable=False)
    viable_options_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    next_action: Mapped[str] = mapped_column(Text, nullable=False)
    source_refs_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    # `standard` (default) or `unblock`. The canonical output lives in
    # `response_json`; the top-level columns above are kept populated for
    # backward compatibility (unblock mode synthesises them from the
    # recommended alternative).
    recommendation_type: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="standard"
    )
    # Hex sha256 of the normalised input context so we can detect that
    # "nothing changed" without rebuilding the context every request.
    input_context_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Full structured response, including the mode-specific keys
    # (unblock analysis, recommendation_context metadata).
    response_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DailyRollup(Base):
    """Phase 1 internal preview snapshot; no outbound delivery."""

    __tablename__ = "daily_rollups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    summary_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    preview_text: Mapped[str] = mapped_column(Text, nullable=False)


class ReviewSession(Base):
    __tablename__ = "review_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    owner_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    reviewer: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    action_items: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    cadence_type: Mapped[str] = mapped_column(String(50), nullable=False, server_default="ad_hoc")
    next_review_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class StandardScore(Base):
    """Seven Standards + Five Emotional Signatures scoring (Phase 1: manual entry)."""

    __tablename__ = "standard_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    scope_id: Mapped[str] = mapped_column(String(255), nullable=False, server_default="default")
    metric_type: Mapped[str] = mapped_column(String(50), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(255), nullable=False)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assessment: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    period: Mapped[str] = mapped_column(String(50), nullable=False, server_default="current")
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False, server_default="system")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MailboxSource(Base):
    __tablename__ = "mailbox_sources"
    __table_args__ = (
        UniqueConstraint("provider", "mailbox_owner", "folder_name", name="uq_mailbox_sources_scope"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    mailbox_owner: Mapped[str] = mapped_column(String(255), nullable=False)
    folder_name: Mapped[str] = mapped_column(String(255), nullable=False, server_default="Inbox")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class MailboxThread(Base):
    __tablename__ = "mailbox_threads"
    __table_args__ = (
        UniqueConstraint(
            "mailbox_source_id",
            "external_thread_id",
            name="uq_mailbox_threads_source_external_thread",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mailbox_source_id: Mapped[int] = mapped_column(
        ForeignKey("mailbox_sources.id"), nullable=False, index=True
    )
    external_thread_id: Mapped[str] = mapped_column(String(512), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_refresh_up_to_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MailboxMessage(Base):
    __tablename__ = "mailbox_messages"
    __table_args__ = (
        UniqueConstraint(
            "mailbox_source_id",
            "external_message_id",
            name="uq_mailbox_messages_source_external_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mailbox_source_id: Mapped[int] = mapped_column(
        ForeignKey("mailbox_sources.id"), nullable=False, index=True
    )
    mailbox_thread_id: Mapped[int] = mapped_column(
        ForeignKey("mailbox_threads.id"), nullable=False, index=True
    )
    external_message_id: Mapped[str] = mapped_column(String(512), nullable=False)
    external_thread_id: Mapped[str] = mapped_column(String(512), nullable=False)
    mailbox_owner: Mapped[str] = mapped_column(String(255), nullable=False)
    folder_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sender: Mapped[str] = mapped_column(String(512), nullable=False)
    recipients_json: Mapped[list] = mapped_column(JSON, nullable=False)
    subject: Mapped[str] = mapped_column(String(1024), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_documents.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MailboxSyncState(Base):
    __tablename__ = "mailbox_sync_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mailbox_source_id: Mapped[int] = mapped_column(
        ForeignKey("mailbox_sources.id"), nullable=False, unique=True, index=True
    )
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cursor_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="idle")
