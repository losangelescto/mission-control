from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime


class ReadyResponse(BaseModel):
    status: str
    database: str


class InfoResponse(BaseModel):
    version: str
    environment: str
    uptime_seconds: float


class ErrorResponse(BaseModel):
    detail: str


TaskStatus = Literal["backlog", "up_next", "in_progress", "blocked", "completed"]
SourceType = Literal[
    "canon_doc",
    "thread_export",
    "transcript",
    "note",
    "board_seed",
    "mail_message",
    "summary_doc",
    "manual_notes",
]

CallArtifactType = Literal["transcript", "summary_doc", "manual_notes"]


class TaskCreate(BaseModel):
    title: str
    description: str
    objective: str
    standard: str
    status: TaskStatus
    priority: str
    owner_name: str
    assigner_name: str
    due_at: datetime | None = None
    source_confidence: float | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    objective: str | None = None
    standard: str | None = None
    status: TaskStatus | None = None
    priority: str | None = None
    owner_name: str | None = None
    assigner_name: str | None = None
    due_at: datetime | None = None
    source_confidence: float | None = None


class TaskResponse(BaseModel):
    id: int
    title: str
    description: str
    objective: str
    standard: str
    status: TaskStatus
    priority: str
    owner_name: str
    assigner_name: str
    due_at: datetime | None = None
    source_confidence: float | None = None
    canon_update_pending: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskFilterOptionsResponse(BaseModel):
    """Static filter dimensions + distinct owner_name values for task list UI."""

    statuses: list[str]
    priorities: list[str]
    owners: list[str]


class TaskUpdateCreate(BaseModel):
    update_type: str
    summary: str
    what_happened: str
    options_considered: str
    steps_taken: str
    next_step: str
    created_by: str


class TaskUpdateResponse(BaseModel):
    id: int
    task_id: int
    update_type: str
    summary: str
    what_happened: str
    options_considered: str
    steps_taken: str
    next_step: str
    created_by: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskBlockRequest(BaseModel):
    blocker_type: str
    blocker_reason: str
    severity: str


class TaskUnblockRequest(BaseModel):
    resolution_notes: str
    next_status: TaskStatus | None = None


class TaskDelegateRequest(BaseModel):
    delegated_to: str
    delegated_by: str


class RecurrenceTemplateCreate(BaseModel):
    title: str
    description: str
    cadence: str
    default_owner_name: str
    default_assigner_name: str
    default_due_window_days: int
    is_active: bool = True


class RecurrenceTemplateResponse(BaseModel):
    id: int
    title: str
    description: str
    cadence: str
    default_owner_name: str
    default_assigner_name: str
    default_due_window_days: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class RecurrenceSpawnResponse(BaseModel):
    recurrence_template_id: int
    occurrence_id: int
    task: TaskResponse


class SourceDocumentResponse(BaseModel):
    id: int
    filename: str
    source_type: SourceType
    canonical_doc_id: str | None = None
    version_label: str | None = None
    is_active_canon_version: bool
    extracted_text: str
    source_path: str
    processing_status: str = "complete"
    pages_processed: int = 0
    pages_total: int = 0
    processing_error: str | None = None
    processing_metadata: dict | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SourceUploadResponse(BaseModel):
    """Response from POST /sources/upload.

    The upload endpoint enqueues the document for background processing
    and returns immediately. ``chunk_count`` is 0 at this point; clients
    poll GET /sources/{id}/status for progress.
    """
    source_document: SourceDocumentResponse
    chunk_count: int = 0


class SourceStatusResponse(BaseModel):
    id: int
    processing_status: str
    pages_processed: int
    pages_total: int
    processing_error: str | None = None
    duration_seconds: float | None = None
    transcription_segments_count: int | None = None

    model_config = ConfigDict(from_attributes=True)


class CanonRegisterRequest(BaseModel):
    canonical_doc_id: str
    version_label: str


class CanonHistoryResponse(BaseModel):
    canonical_doc_id: str
    versions: list[SourceDocumentResponse]


class TaskCandidateResponse(BaseModel):
    id: int
    source_document_id: int
    title: str
    description: str
    inferred_owner_name: str | None = None
    inferred_due_at: datetime | None = None
    fallback_due_at: datetime | None = None
    review_status: str
    confidence: float | None = None
    hints_json: dict = {}
    candidate_kind: str = "new_task"
    mailbox_message_id: int | None = None
    mailbox_thread_id: int | None = None
    related_task_id: int | None = None
    call_artifact_id: int | None = None
    suggested_priority: str | None = None
    source_reference: str | None = None
    source_timestamp: str | None = None
    canon_alignment: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CanonChangeEventSummary(BaseModel):
    id: int
    canon_doc_id: str
    previous_source_id: int | None = None
    new_source_id: int
    change_summary: str
    affected_task_ids: list[int]
    impact_analysis: str
    reviewed: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CanonChangeEventDetail(CanonChangeEventSummary):
    affected_tasks: list[TaskResponse] = []
    new_source_filename: str | None = None
    previous_source_filename: str | None = None


class CanonChangeListResponse(BaseModel):
    events: list[CanonChangeEventSummary]
    unreviewed_count: int


class TaskCandidateRejectRequest(BaseModel):
    reason: str | None = None


class MailboxThreadRefreshResponse(BaseModel):
    mailbox_thread_id: int
    external_thread_id: str
    candidates: list[TaskCandidateResponse]


class CallArtifactResponse(BaseModel):
    id: int
    artifact_type: str
    title: str | None
    source_document_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CallArtifactDetailResponse(BaseModel):
    id: int
    artifact_type: str
    title: str | None
    source_document_id: int
    created_at: datetime
    source_document: SourceDocumentResponse

    model_config = ConfigDict(from_attributes=True)


class CallArtifactUploadResponse(BaseModel):
    call_artifact: CallArtifactResponse
    chunk_count: int = 0


class EmbeddingResponse(BaseModel):
    source_document_id: int
    embedded_chunk_count: int


class RetrieveSearchRequest(BaseModel):
    query: str
    active_canon_only: bool = False
    source_types: list[SourceType] | None = None


class RetrievedChunkResponse(BaseModel):
    source_document_id: int
    source_filename: str
    source_type: str
    canonical_doc_id: str | None = None
    version_label: str | None = None
    is_active_canon_version: bool
    chunk_index: int
    chunk_text: str
    score: float


class RetrieveSearchResponse(BaseModel):
    query: str
    results: list[RetrievedChunkResponse]


class UnblockAlternative(BaseModel):
    path: str
    solves: str
    tradeoff: str
    first_step: str
    aligned_standard: str


class UnblockAnalysis(BaseModel):
    blocker_summary: str
    root_cause_analysis: str
    alternatives: list[UnblockAlternative]
    recommended_path: str
    canon_reference: str


class RecommendationContextMeta(BaseModel):
    canon_chunks_used: int
    updates_included: int
    reviews_included: int
    blocker_active: bool
    subtasks_total: int = 0
    subtasks_completed: int = 0
    active_obstacles: int = 0
    # Number of recently-resolved obstacles whose description, impact, and
    # resolution_notes were injected into the recommendation prompt. Lets
    # the UI show "the LLM saw your resolution" and lets tests verify the
    # plumbing without parsing the prompt body.
    resolved_obstacles_included: int = 0


class RecommendationResponse(BaseModel):
    id: int
    task_id: int
    objective: str
    standard: str
    first_principles_plan: str
    viable_options: list[str]
    next_action: str
    source_refs: list[dict]
    created_at: datetime
    recommendation_type: str = "standard"
    recommendation_context: RecommendationContextMeta | None = None
    unblock_analysis: UnblockAnalysis | None = None


class RecommendationHistoryItem(BaseModel):
    id: int
    task_id: int
    recommendation_type: str
    created_at: datetime
    objective: str
    standard: str
    next_action: str


class DailyReviewItem(BaseModel):
    task_id: int
    title: str
    owner_name: str
    status: str
    priority: str
    due_at: datetime | None = None
    reason: str


class DailyReviewResponse(BaseModel):
    urgent: list[DailyReviewItem]
    blocked: list[DailyReviewItem]
    stale: list[DailyReviewItem]
    due_soon: list[DailyReviewItem]
    recurring_due: list[dict]
    candidate_review: list[TaskCandidateResponse]


class DailyRollupPreviewResponse(BaseModel):
    """Phase 1 internal preview; not routed to recipients; no outbound notifications."""

    summary: dict
    preview_text: str
    phase: Literal["preview_only"] = "preview_only"


class DailyRollupGeneratedResponse(BaseModel):
    """Persisted daily roll-up row (preview phase)."""

    id: int
    generated_at: datetime
    summary: dict
    preview_text: str
    phase: Literal["preview_only"] = "preview_only"


class OwnerMetrics(BaseModel):
    owner_name: str
    total_tasks: int
    completed_tasks: int
    completion_rate: float
    overdue_tasks: int
    blocked_tasks: int
    delegation_count: int
    delegation_drift_count: int


class MetricsSummaryResponse(BaseModel):
    average_task_age_days: float
    overdue_count: int
    blocked_count: int
    repeat_misses: int
    candidate_review_queue_size: int
    total_tasks: int


class MetricsByOwnerResponse(BaseModel):
    owners: list[OwnerMetrics]


# --- Mailbox (Phase 1) ---


class MailboxSyncFixtureMessage(BaseModel):
    """Request body item: thread_id is the external conversation/thread id."""

    external_message_id: str
    thread_id: str
    mailbox_owner: str
    folder_name: str | None = None
    sender: str
    recipients_json: list[str] = []
    subject: str
    body_text: str
    received_at: datetime


class MailboxSyncFixtureRequest(BaseModel):
    mailbox_owner: str
    folder_name: str | None = None
    messages: list[MailboxSyncFixtureMessage] | None = None


class MailboxSyncFixtureResponse(BaseModel):
    mailbox_source_id: int
    inserted: int
    skipped_duplicates: int


class MailboxMessageResponse(BaseModel):
    id: int
    mailbox_source_id: int
    mailbox_thread_id: int
    external_message_id: str
    external_thread_id: str
    mailbox_owner: str
    folder_name: str
    sender: str
    recipients_json: list
    subject: str
    body_text: str
    received_at: datetime
    source_document_id: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MailboxThreadSummary(BaseModel):
    id: int
    mailbox_source_id: int
    external_thread_id: str
    subject: str | None
    last_message_at: datetime
    message_count: int


class MailboxThreadDetailResponse(BaseModel):
    thread: MailboxThreadSummary
    messages: list[MailboxMessageResponse]


# ─── Standard Scores ──────────────────────────────────────

ScopeType = Literal["company", "community", "team", "person"]
MetricType = Literal["standard", "signature"]


class StandardScoreCreate(BaseModel):
    scope_type: ScopeType
    scope_id: str = "default"
    metric_type: MetricType
    metric_name: str
    score: int | None = None
    assessment: str = ""
    period: str = "current"
    updated_by: str = "system"


class StandardScoreResponse(BaseModel):
    id: int
    scope_type: str
    scope_id: str
    metric_type: str
    metric_name: str
    score: int | None
    assessment: str
    period: str
    updated_by: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Review Sessions ───────────────────────────────────────

ReviewCadenceType = Literal["daily", "weekly", "monthly", "quarterly", "ad_hoc"]


class ReviewSessionCreate(BaseModel):
    task_id: int | None = None
    owner_name: str | None = None
    reviewer: str
    notes: str
    action_items: str = ""
    cadence_type: ReviewCadenceType = "ad_hoc"
    next_review_date: date | None = None


class ReviewSessionResponse(BaseModel):
    id: int
    task_id: int | None
    owner_name: str | None
    reviewer: str
    notes: str
    action_items: str
    cadence_type: str
    next_review_date: date | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Sub-tasks ──────────────────────────────────────────────────────────


SubTaskStatus = Literal["pending", "in_progress", "completed"]


class SubTaskCreate(BaseModel):
    title: str
    description: str = ""
    canon_reference: str = ""
    status: SubTaskStatus = "pending"
    order: int | None = None  # None → appended to the end


class SubTaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    canon_reference: str | None = None
    status: SubTaskStatus | None = None
    order: int | None = None


class SubTaskResponse(BaseModel):
    id: int
    parent_task_id: int
    title: str
    description: str
    status: str
    order: int
    canon_reference: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SubTaskDraft(BaseModel):
    """A proposed sub-task from the LLM, not yet persisted."""
    title: str
    description: str
    canon_reference: str


class SubTaskGeneratePreviewResponse(BaseModel):
    task_id: int
    drafts: list[SubTaskDraft]


# ─── Obstacles ──────────────────────────────────────────────────────────


ObstacleStatus = Literal["active", "resolved"]
ObstacleSolutionSource = Literal["manual", "ai_generated"]


class ObstacleSolution(BaseModel):
    solution: str
    trade_off: str = ""
    first_step: str = ""
    aligned_standard: str = ""
    source: ObstacleSolutionSource = "manual"


class ObstacleCreate(BaseModel):
    description: str
    impact: str = ""
    identified_by: str = "user"
    proposed_solutions: list[ObstacleSolution] = []


class ObstacleUpdate(BaseModel):
    description: str | None = None
    impact: str | None = None
    status: ObstacleStatus | None = None
    resolution_notes: str | None = None


class ObstacleResolveRequest(BaseModel):
    resolution_notes: str


class ObstacleResponse(BaseModel):
    id: int
    task_id: int
    description: str
    impact: str
    status: str
    proposed_solutions: list[ObstacleSolution]
    resolution_notes: str
    identified_at: datetime
    resolved_at: datetime | None
    identified_by: str

    model_config = ConfigDict(from_attributes=True)


class AuditEventResponse(BaseModel):
    id: int
    entity_type: str
    entity_id: str
    action: str
    actor: str
    changes: dict | None = None
    metadata: dict | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditListResponse(BaseModel):
    events: list[AuditEventResponse]
    total: int
    limit: int
    offset: int


SearchResultType = Literal[
    "task", "task_update", "sub_task", "obstacle",
    "source", "source_chunk", "review", "canon",
]


class SearchResult(BaseModel):
    id: int
    type: SearchResultType
    title: str
    snippet: str
    relevance: float
    url: str
    metadata: dict


class SearchResponse(BaseModel):
    query: str
    mode: Literal["keyword", "semantic"]
    type_filter: str
    results: list[SearchResult]
    total: int
    type_counts: dict[str, int]
    limit: int
    offset: int
