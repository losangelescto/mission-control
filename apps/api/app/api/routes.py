import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.security import limiter
from app.deps import get_call_extraction_extractor, get_mail_extraction_extractor
from app.db import get_db
from app.mailbox.service import (
    get_mailbox_message,
    get_thread_by_external,
    sync_fixture_mail,
    sync_fixture_mail_from_dtos,
)
from app.mailbox.types import MailboxMessageDTO
from app.mailbox.repository import list_messages
from app.schemas import (
    CanonHistoryResponse,
    CanonRegisterRequest,
    HealthResponse,
    InfoResponse,
    RecurrenceSpawnResponse,
    RecurrenceTemplateCreate,
    RecurrenceTemplateResponse,
    ReadyResponse,
    SourceDocumentResponse,
    SourceType,
    SourceUploadResponse,
    TaskBlockRequest,
    TaskCandidateRejectRequest,
    TaskCandidateResponse,
    TaskCreate,
    TaskDelegateRequest,
    TaskFilterOptionsResponse,
    TaskResponse,
    TaskStatus,
    TaskUnblockRequest,
    TaskUpdateCreate,
    TaskUpdateResponse,
    TaskUpdate,
    EmbeddingResponse,
    RetrieveSearchRequest,
    RetrieveSearchResponse,
    RetrievedChunkResponse,
    RecommendationContextMeta,
    RecommendationHistoryItem,
    RecommendationResponse,
    UnblockAlternative,
    UnblockAnalysis,
    DailyReviewResponse,
    DailyReviewItem,
    DailyRollupPreviewResponse,
    DailyRollupGeneratedResponse,
    MetricsByOwnerResponse,
    MetricsSummaryResponse,
    OwnerMetrics,
    MailboxMessageResponse,
    MailboxSyncFixtureRequest,
    MailboxSyncFixtureResponse,
    MailboxThreadDetailResponse,
    MailboxThreadSummary,
    MailboxThreadRefreshResponse,
    CallArtifactType,
    CallArtifactResponse,
    CallArtifactDetailResponse,
    CallArtifactUploadResponse,
    ReviewSessionCreate,
    ReviewSessionResponse,
    StandardScoreCreate,
    StandardScoreResponse,
    SubTaskCreate,
    SubTaskGeneratePreviewResponse,
    SubTaskResponse,
    SubTaskUpdate,
    ObstacleCreate,
    ObstacleResolveRequest,
    ObstacleResponse,
    ObstacleUpdate,
)
from app.task_candidate_extraction import AIExtractionInterface
from app.repositories import (
    create_review_session as repo_create_review_session,
    list_review_sessions as repo_list_review_sessions,
    create_standard_score as repo_create_standard_score,
    list_standard_scores as repo_list_standard_scores,
)
from app.services import (
    activate_canon_source,
    approve_task_candidate,
    dismiss_task_candidate,
    block_task,
    create_recurrence_template,
    create_task,
    create_task_update,
    embed_source_chunks,
    delegate_task,
    get_canon_history,
    get_readiness,
    list_active_canon_sources,
    register_canon_source,
    get_source_document,
    get_task,
    extract_task_candidates_from_source,
    extract_task_candidates_from_mail_message,
    refresh_mail_thread_task_state,
    ThreadStateSuggestionApprovalError,
    extract_actions_from_call_artifact,
    get_call_artifact,
    ingest_call_artifact_upload,
    list_call_artifacts,
    ingest_source_upload,
    analyze_obstacle_by_id,
    create_obstacle_for_task,
    create_sub_task_for_task,
    delete_sub_task_by_id,
    generate_sub_tasks_preview,
    list_obstacles,
    list_sub_tasks,
    list_task_candidates,
    list_task_recommendations,
    resolve_obstacle_by_id,
    update_obstacle_by_id,
    update_sub_task_by_id,
    list_source_documents,
    list_recurrence_templates,
    list_task_updates,
    list_tasks,
    reject_task_candidate,
    retrieve_search,
    generate_task_recommendation,
    get_daily_review,
    get_daily_rollup_preview,
    generate_daily_rollup,
    get_task_filter_options,
    get_metrics_summary,
    get_metrics_by_owner,
    spawn_recurrence_template,
    unblock_task,
    update_task,
)

router = APIRouter()

_STARTUP_MONOTONIC = time.monotonic()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", timestamp=datetime.now(timezone.utc))


@router.get("/ready", response_model=ReadyResponse)
def ready(db: Session = Depends(get_db)) -> ReadyResponse:
    if not get_readiness(db):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "database": "disconnected"},
        )
    return ReadyResponse(status="ready", database="connected")


@router.get("/info", response_model=InfoResponse)
def info() -> InfoResponse:
    settings = get_settings()
    return InfoResponse(
        version=settings.app_version,
        environment=settings.app_env,
        uptime_seconds=round(time.monotonic() - _STARTUP_MONOTONIC, 3),
    )


@router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task_route(payload: TaskCreate, db: Session = Depends(get_db)) -> TaskResponse:
    created = create_task(db, payload.model_dump())
    return TaskResponse.model_validate(created)


@router.get("/tasks", response_model=list[TaskResponse])
def list_tasks_route(
    status: TaskStatus | None = Query(default=None),
    owner_name: str | None = Query(default=None),
    due_before: datetime | None = Query(default=None),
    priority: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[TaskResponse]:
    tasks = list_tasks(
        db=db, status=status, owner_name=owner_name, due_before=due_before, priority=priority
    )
    return [TaskResponse.model_validate(task) for task in tasks]


@router.get("/tasks/filter-options", response_model=TaskFilterOptionsResponse)
def task_filter_options_route(db: Session = Depends(get_db)) -> TaskFilterOptionsResponse:
    statuses, priorities, owners = get_task_filter_options(db)
    return TaskFilterOptionsResponse(statuses=statuses, priorities=priorities, owners=owners)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task_route(task_id: int, db: Session = Depends(get_db)) -> TaskResponse:
    task = get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    return TaskResponse.model_validate(task)


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
def update_task_route(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db)) -> TaskResponse:
    updated = update_task(db, task_id=task_id, updates=payload.model_dump(exclude_unset=True))
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    return TaskResponse.model_validate(updated)


@router.post("/tasks/{task_id}/updates", response_model=TaskUpdateResponse, status_code=status.HTTP_201_CREATED)
def create_task_update_route(
    task_id: int, payload: TaskUpdateCreate, db: Session = Depends(get_db)
) -> TaskUpdateResponse:
    created = create_task_update(db, task_id=task_id, payload=payload.model_dump())
    if created is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    return TaskUpdateResponse.model_validate(created)


@router.get("/tasks/{task_id}/updates", response_model=list[TaskUpdateResponse])
def list_task_updates_route(task_id: int, db: Session = Depends(get_db)) -> list[TaskUpdateResponse]:
    updates = list_task_updates(db, task_id=task_id)
    if updates is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    return [TaskUpdateResponse.model_validate(update) for update in updates]


@router.post("/tasks/{task_id}/block", response_model=TaskResponse)
def block_task_route(task_id: int, payload: TaskBlockRequest, db: Session = Depends(get_db)) -> TaskResponse:
    blocked = block_task(db, task_id=task_id, payload=payload.model_dump())
    if blocked is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    return TaskResponse.model_validate(blocked)


@router.post("/tasks/{task_id}/unblock", response_model=TaskResponse)
def unblock_task_route(
    task_id: int, payload: TaskUnblockRequest, db: Session = Depends(get_db)
) -> TaskResponse:
    unblocked = unblock_task(
        db,
        task_id=task_id,
        resolution_notes=payload.resolution_notes,
        next_status=payload.next_status,
    )
    if unblocked is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task or open blocker not found")
    return TaskResponse.model_validate(unblocked)


@router.post("/tasks/{task_id}/delegate", response_model=TaskResponse)
def delegate_task_route(
    task_id: int, payload: TaskDelegateRequest, db: Session = Depends(get_db)
) -> TaskResponse:
    delegated = delegate_task(
        db,
        task_id=task_id,
        delegated_to=payload.delegated_to,
        delegated_by=payload.delegated_by,
    )
    if delegated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    return TaskResponse.model_validate(delegated)


@router.post(
    "/recurrence-templates",
    response_model=RecurrenceTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_recurrence_template_route(
    payload: RecurrenceTemplateCreate, db: Session = Depends(get_db)
) -> RecurrenceTemplateResponse:
    created = create_recurrence_template(db, payload.model_dump())
    return RecurrenceTemplateResponse.model_validate(created)


@router.get("/recurrence-templates", response_model=list[RecurrenceTemplateResponse])
def list_recurrence_templates_route(db: Session = Depends(get_db)) -> list[RecurrenceTemplateResponse]:
    templates = list_recurrence_templates(db)
    return [RecurrenceTemplateResponse.model_validate(template) for template in templates]


@router.post("/recurrence-templates/{recurrence_template_id}/spawn", response_model=RecurrenceSpawnResponse)
def spawn_recurrence_template_route(
    recurrence_template_id: int, db: Session = Depends(get_db)
) -> RecurrenceSpawnResponse:
    result = spawn_recurrence_template(db, recurrence_template_id=recurrence_template_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="recurrence template not found")
    task, occurrence_id = result
    return RecurrenceSpawnResponse(
        recurrence_template_id=recurrence_template_id,
        occurrence_id=occurrence_id,
        task=TaskResponse.model_validate(task),
    )


@router.post("/sources/upload", response_model=SourceUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_source_route(
    source_type: SourceType = Form(...),
    file: UploadFile = File(...),
    canonical_doc_id: str | None = Form(default=None),
    version_label: str | None = Form(default=None),
    is_active_canon_version: bool = Form(default=False),
    db: Session = Depends(get_db),
) -> SourceUploadResponse:
    file_bytes = await file.read()
    try:
        source_document, chunk_count = ingest_source_upload(
            db,
            filename=file.filename or "upload",
            source_type=source_type,
            file_bytes=file_bytes,
            canonical_doc_id=canonical_doc_id,
            version_label=version_label,
            is_active_canon_version=is_active_canon_version,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return SourceUploadResponse(
        source_document=SourceDocumentResponse.model_validate(source_document),
        chunk_count=chunk_count,
    )


@router.get("/sources", response_model=list[SourceDocumentResponse])
def list_sources_route(db: Session = Depends(get_db)) -> list[SourceDocumentResponse]:
    sources = list_source_documents(db)
    return [SourceDocumentResponse.model_validate(source) for source in sources]


@router.get("/sources/{source_id}", response_model=SourceDocumentResponse)
def get_source_route(source_id: int, db: Session = Depends(get_db)) -> SourceDocumentResponse:
    source_document = get_source_document(db, source_id)
    if source_document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source not found")
    return SourceDocumentResponse.model_validate(source_document)


@router.post("/canon/register/{source_id}", response_model=SourceDocumentResponse)
def register_canon_route(
    source_id: int, payload: CanonRegisterRequest, db: Session = Depends(get_db)
) -> SourceDocumentResponse:
    try:
        source_document = register_canon_source(
            db,
            source_id=source_id,
            canonical_doc_id=payload.canonical_doc_id,
            version_label=payload.version_label,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if source_document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source not found")
    return SourceDocumentResponse.model_validate(source_document)


@router.post("/canon/activate/{source_id}", response_model=SourceDocumentResponse)
def activate_canon_route(source_id: int, db: Session = Depends(get_db)) -> SourceDocumentResponse:
    try:
        source_document = activate_canon_source(db, source_id=source_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if source_document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source not found")
    return SourceDocumentResponse.model_validate(source_document)


@router.get("/canon/active", response_model=list[SourceDocumentResponse])
def list_active_canon_route(db: Session = Depends(get_db)) -> list[SourceDocumentResponse]:
    sources = list_active_canon_sources(db)
    return [SourceDocumentResponse.model_validate(source) for source in sources]


@router.get("/canon/history/{canonical_doc_id}", response_model=CanonHistoryResponse)
def canon_history_route(canonical_doc_id: str, db: Session = Depends(get_db)) -> CanonHistoryResponse:
    versions = get_canon_history(db, canonical_doc_id=canonical_doc_id)
    return CanonHistoryResponse(
        canonical_doc_id=canonical_doc_id,
        versions=[SourceDocumentResponse.model_validate(v) for v in versions],
    )


@router.post("/sources/{source_id}/extract-task-candidates", response_model=list[TaskCandidateResponse])
def extract_task_candidates_route(
    source_id: int, db: Session = Depends(get_db)
) -> list[TaskCandidateResponse]:
    candidates = extract_task_candidates_from_source(db, source_id=source_id)
    if candidates is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source not found")
    return [TaskCandidateResponse.model_validate(candidate) for candidate in candidates]


@router.get("/task-candidates", response_model=list[TaskCandidateResponse])
def list_task_candidates_route(
    review_status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[TaskCandidateResponse]:
    candidates = list_task_candidates(db, review_status=review_status)
    return [TaskCandidateResponse.model_validate(candidate) for candidate in candidates]


@router.post("/task-candidates/{candidate_id}/approve", response_model=TaskResponse)
def approve_task_candidate_route(candidate_id: int, db: Session = Depends(get_db)) -> TaskResponse:
    try:
        task = approve_task_candidate(db, candidate_id=candidate_id)
    except ThreadStateSuggestionApprovalError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="thread_state_suggestion candidates require manual review; no task was created",
        ) from exc
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task candidate not found")
    return TaskResponse.model_validate(task)


@router.post("/task-candidates/{candidate_id}/reject", response_model=TaskCandidateResponse)
def reject_task_candidate_route(
    candidate_id: int,
    payload: TaskCandidateRejectRequest,
    db: Session = Depends(get_db),
) -> TaskCandidateResponse:
    candidate = reject_task_candidate(db, candidate_id=candidate_id, reason=payload.reason)
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task candidate not found")
    return TaskCandidateResponse.model_validate(candidate)


@router.post("/task-candidates/{candidate_id}/dismiss", response_model=TaskCandidateResponse)
def dismiss_task_candidate_route(
    candidate_id: int, db: Session = Depends(get_db)
) -> TaskCandidateResponse:
    candidate = dismiss_task_candidate(db, candidate_id=candidate_id)
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task candidate not found")
    return TaskCandidateResponse.model_validate(candidate)


@router.post("/sources/{source_id}/embed", response_model=EmbeddingResponse)
def embed_source_route(source_id: int, db: Session = Depends(get_db)) -> EmbeddingResponse:
    count = embed_source_chunks(db, source_id=source_id)
    if count is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source not found")
    return EmbeddingResponse(source_document_id=source_id, embedded_chunk_count=count)


@router.post("/retrieve/search", response_model=RetrieveSearchResponse)
def retrieve_search_route(payload: RetrieveSearchRequest, db: Session = Depends(get_db)) -> RetrieveSearchResponse:
    results = retrieve_search(
        db,
        query=payload.query,
        active_canon_only=payload.active_canon_only,
        source_types=payload.source_types,
    )
    return RetrieveSearchResponse(
        query=payload.query,
        results=[RetrievedChunkResponse(**row) for row in results],
    )


def _recommendation_to_response(recommendation) -> RecommendationResponse:  # type: ignore[no-untyped-def]
    """Project a Recommendation row into the public response shape.

    The stored row always has the classic columns populated (for backward
    compatibility with downstream consumers). When ``response_json`` is
    present we also surface the mode-specific metadata and, for unblock
    mode, the full analysis object.
    """
    response_json = recommendation.response_json or {}
    meta = response_json.get("recommendation_context")
    unblock: UnblockAnalysis | None = None
    if recommendation.recommendation_type == "unblock":
        unblock = UnblockAnalysis(
            blocker_summary=response_json.get("blocker_summary", ""),
            root_cause_analysis=response_json.get("root_cause_analysis", ""),
            alternatives=[
                UnblockAlternative(**alt) for alt in response_json.get("alternatives", [])
            ],
            recommended_path=response_json.get("recommended_path", ""),
            canon_reference=response_json.get("canon_reference", ""),
        )
    return RecommendationResponse(
        id=recommendation.id,
        task_id=recommendation.task_id,
        objective=recommendation.objective,
        standard=recommendation.standard,
        first_principles_plan=recommendation.first_principles_plan,
        viable_options=recommendation.viable_options_json,
        next_action=recommendation.next_action,
        source_refs=recommendation.source_refs_json,
        created_at=recommendation.created_at,
        recommendation_type=recommendation.recommendation_type,
        recommendation_context=RecommendationContextMeta(**meta) if meta else None,
        unblock_analysis=unblock,
    )


@router.post("/tasks/{task_id}/recommendation", response_model=RecommendationResponse)
@limiter.limit(lambda: get_settings().rate_limit_recommendation)
def generate_recommendation_route(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db),
) -> RecommendationResponse:
    recommendation = generate_task_recommendation(db, task_id=task_id)
    if recommendation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    return _recommendation_to_response(recommendation)


@router.get("/tasks/{task_id}/recommendations", response_model=list[RecommendationHistoryItem])
def list_task_recommendations_route(
    task_id: int, db: Session = Depends(get_db)
) -> list[RecommendationHistoryItem]:
    task = get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    rows = list_task_recommendations(db, task_id=task_id, limit=20)
    return [
        RecommendationHistoryItem(
            id=r.id,
            task_id=r.task_id,
            recommendation_type=r.recommendation_type,
            created_at=r.created_at,
            objective=r.objective,
            standard=r.standard,
            next_action=r.next_action,
        )
        for r in rows
    ]


@router.get("/review/daily", response_model=DailyReviewResponse)
def daily_review_route(db: Session = Depends(get_db)) -> DailyReviewResponse:
    data = get_daily_review(db)
    return DailyReviewResponse(
        urgent=[DailyReviewItem(**item) for item in data["urgent"]],
        blocked=[DailyReviewItem(**item) for item in data["blocked"]],
        stale=[DailyReviewItem(**item) for item in data["stale"]],
        due_soon=[DailyReviewItem(**item) for item in data["due_soon"]],
        recurring_due=data["recurring_due"],
        candidate_review=[TaskCandidateResponse.model_validate(candidate) for candidate in data["candidate_review"]],
    )


@router.get("/rollups/daily/preview", response_model=DailyRollupPreviewResponse)
def daily_rollup_preview_route(db: Session = Depends(get_db)) -> DailyRollupPreviewResponse:
    data = get_daily_rollup_preview(db)
    return DailyRollupPreviewResponse(
        summary=data["summary"],
        preview_text=data["preview_text"],
        phase=data["phase"],
    )


@router.post(
    "/rollups/daily/generate",
    response_model=DailyRollupGeneratedResponse,
    status_code=status.HTTP_201_CREATED,
)
def daily_rollup_generate_route(db: Session = Depends(get_db)) -> DailyRollupGeneratedResponse:
    row = generate_daily_rollup(db)
    return DailyRollupGeneratedResponse(
        id=row.id,
        generated_at=row.generated_at,
        summary=row.summary_json,
        preview_text=row.preview_text,
        phase="preview_only",
    )


@router.get("/metrics/summary", response_model=MetricsSummaryResponse)
def metrics_summary_route(db: Session = Depends(get_db)) -> MetricsSummaryResponse:
    return MetricsSummaryResponse(**get_metrics_summary(db))


@router.get("/metrics/by-owner", response_model=MetricsByOwnerResponse)
def metrics_by_owner_route(db: Session = Depends(get_db)) -> MetricsByOwnerResponse:
    owners = [OwnerMetrics(**row) for row in get_metrics_by_owner(db)]
    return MetricsByOwnerResponse(owners=owners)


@router.post("/mail/sync-fixture", response_model=MailboxSyncFixtureResponse, status_code=status.HTTP_200_OK)
def mail_sync_fixture_route(
    payload: MailboxSyncFixtureRequest, db: Session = Depends(get_db)
) -> MailboxSyncFixtureResponse:
    if not get_settings().use_fixture_mailbox:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Fixture mailbox sync is disabled (USE_FIXTURE_MAILBOX=false).",
        )
    resolved_folder = payload.folder_name or "Inbox"
    if payload.messages:
        dtos: list[MailboxMessageDTO] = []
        for m in payload.messages:
            dtos.append(
                MailboxMessageDTO(
                    external_message_id=m.external_message_id,
                    external_thread_id=m.thread_id,
                    mailbox_owner=m.mailbox_owner,
                    folder_name=m.folder_name or resolved_folder,
                    sender=m.sender,
                    recipients_json=list(m.recipients_json),
                    subject=m.subject,
                    body_text=m.body_text,
                    received_at=m.received_at,
                )
            )
        source, inserted, skipped = sync_fixture_mail_from_dtos(
            db,
            mailbox_owner=payload.mailbox_owner,
            folder_name=payload.folder_name,
            dtos=dtos,
        )
    else:
        source, inserted, skipped = sync_fixture_mail(
            db,
            mailbox_owner=payload.mailbox_owner,
            folder_name=payload.folder_name,
        )
    return MailboxSyncFixtureResponse(
        mailbox_source_id=source.id,
        inserted=inserted,
        skipped_duplicates=skipped,
    )


@router.get("/mail/messages", response_model=list[MailboxMessageResponse])
def list_mail_messages_route(
    mailbox_owner: str | None = Query(default=None),
    mailbox_source_id: int | None = Query(default=None),
    thread_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[MailboxMessageResponse]:
    rows = list_messages(
        db,
        mailbox_owner=mailbox_owner,
        mailbox_source_id=mailbox_source_id,
        thread_external_id=thread_id,
    )
    return [MailboxMessageResponse.model_validate(r) for r in rows]


@router.get("/mail/messages/{message_id}", response_model=MailboxMessageResponse)
def get_mail_message_route(message_id: int, db: Session = Depends(get_db)) -> MailboxMessageResponse:
    row = get_mailbox_message(db, message_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="message not found")
    return MailboxMessageResponse.model_validate(row)


@router.get("/mail/threads/{thread_id}", response_model=MailboxThreadDetailResponse)
def get_mail_thread_route(
    thread_id: str,
    mailbox_owner: str = Query(..., description="Mailbox owner (e.g. email)"),
    folder_name: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> MailboxThreadDetailResponse:
    out = get_thread_by_external(
        db,
        mailbox_owner=mailbox_owner,
        folder_name=folder_name,
        external_thread_id=thread_id,
    )
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="thread not found")
    thread, messages = out
    return MailboxThreadDetailResponse(
        thread=MailboxThreadSummary(
            id=thread.id,
            mailbox_source_id=thread.mailbox_source_id,
            external_thread_id=thread.external_thread_id,
            subject=thread.subject,
            last_message_at=thread.last_message_at,
            message_count=len(messages),
        ),
        messages=[MailboxMessageResponse.model_validate(m) for m in messages],
    )


@router.post(
    "/mail/messages/{message_id}/extract-task-candidates",
    response_model=list[TaskCandidateResponse],
)
def extract_mail_message_task_candidates_route(
    message_id: int,
    db: Session = Depends(get_db),
    extractor: AIExtractionInterface = Depends(get_mail_extraction_extractor),
) -> list[TaskCandidateResponse]:
    candidates = extract_task_candidates_from_mail_message(
        db, message_id=message_id, ai_extractor=extractor
    )
    if candidates is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="mail message not found")
    return [TaskCandidateResponse.model_validate(c) for c in candidates]


@router.post(
    "/mail/threads/{thread_id}/refresh-task-state",
    response_model=MailboxThreadRefreshResponse,
)
def refresh_mail_thread_task_state_route(
    thread_id: str,
    mailbox_owner: str = Query(...),
    folder_name: str | None = Query(default=None),
    db: Session = Depends(get_db),
    extractor: AIExtractionInterface = Depends(get_mail_extraction_extractor),
) -> MailboxThreadRefreshResponse:
    thread, candidates = refresh_mail_thread_task_state(
        db,
        external_thread_id=thread_id,
        mailbox_owner=mailbox_owner,
        folder_name=folder_name,
        ai_extractor=extractor,
    )
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="thread not found")
    return MailboxThreadRefreshResponse(
        mailbox_thread_id=thread.id,
        external_thread_id=thread.external_thread_id,
        candidates=[TaskCandidateResponse.model_validate(c) for c in candidates],
    )


@router.post("/calls/upload-artifact", response_model=CallArtifactUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_call_artifact_route(
    artifact_type: CallArtifactType = Form(...),
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> CallArtifactUploadResponse:
    if not get_settings().enable_teams_call_connector:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Call artifact flows are disabled (ENABLE_TEAMS_CALL_CONNECTOR=false).",
        )
    file_bytes = await file.read()
    try:
        ca, chunk_count = ingest_call_artifact_upload(
            db,
            artifact_type=artifact_type,
            filename=file.filename or "artifact.txt",
            file_bytes=file_bytes,
            title=title,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return CallArtifactUploadResponse(
        call_artifact=CallArtifactResponse.model_validate(ca),
        chunk_count=chunk_count,
    )


@router.get("/calls/artifacts", response_model=list[CallArtifactResponse])
def list_call_artifacts_route(db: Session = Depends(get_db)) -> list[CallArtifactResponse]:
    rows = list_call_artifacts(db)
    return [CallArtifactResponse.model_validate(r) for r in rows]


@router.get("/calls/artifacts/{call_artifact_id}", response_model=CallArtifactDetailResponse)
def get_call_artifact_route(call_artifact_id: int, db: Session = Depends(get_db)) -> CallArtifactDetailResponse:
    ca = get_call_artifact(db, call_artifact_id)
    if ca is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="call artifact not found")
    src = get_source_document(db, ca.source_document_id)
    if src is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source document not found")
    return CallArtifactDetailResponse(
        id=ca.id,
        artifact_type=ca.artifact_type,
        title=ca.title,
        source_document_id=ca.source_document_id,
        created_at=ca.created_at,
        source_document=SourceDocumentResponse.model_validate(src),
    )


@router.post(
    "/calls/artifacts/{call_artifact_id}/extract-actions",
    response_model=list[TaskCandidateResponse],
)
def extract_call_actions_route(
    call_artifact_id: int,
    db: Session = Depends(get_db),
    extractor: AIExtractionInterface = Depends(get_call_extraction_extractor),
) -> list[TaskCandidateResponse]:
    if not get_settings().enable_teams_call_connector:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Call artifact flows are disabled (ENABLE_TEAMS_CALL_CONNECTOR=false).",
        )
    candidates = extract_actions_from_call_artifact(
        db, call_artifact_id=call_artifact_id, ai_extractor=extractor
    )
    if candidates is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="call artifact not found")
    return [TaskCandidateResponse.model_validate(c) for c in candidates]


# ─── Review Sessions ──────────────────────────────────────


@router.post("/reviews", response_model=ReviewSessionResponse, status_code=status.HTTP_201_CREATED)
def create_review_route(payload: ReviewSessionCreate, db: Session = Depends(get_db)) -> ReviewSessionResponse:
    data = payload.model_dump()
    session = repo_create_review_session(db, data)
    db.commit()
    db.refresh(session)
    return ReviewSessionResponse.model_validate(session)


@router.get("/reviews", response_model=list[ReviewSessionResponse])
def list_reviews_route(
    task_id: int | None = Query(default=None),
    owner: str | None = Query(default=None),
    cadence_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[ReviewSessionResponse]:
    sessions = repo_list_review_sessions(db, task_id=task_id, owner_name=owner, cadence_type=cadence_type)
    return [ReviewSessionResponse.model_validate(s) for s in sessions]


@router.get("/reviews/cadence-status")
def cadence_status_route(db: Session = Depends(get_db)) -> list[dict]:
    from datetime import UTC
    now = datetime.now(UTC)
    cadences = [
        {"cadence": "daily",     "window_days": 1},
        {"cadence": "weekly",    "window_days": 7},
        {"cadence": "monthly",   "window_days": 30},
        {"cadence": "quarterly", "window_days": 90},
    ]
    result = []
    for c in cadences:
        sessions = repo_list_review_sessions(db, cadence_type=c["cadence"])
        last = sessions[0] if sessions else None
        last_date = last.created_at if last else None
        overdue = True
        if last_date is not None:
            overdue = (now - last_date).days >= c["window_days"]
        result.append({
            "cadence": c["cadence"],
            "window_days": c["window_days"],
            "last_review": last_date.isoformat() if last_date else None,
            "overdue": overdue,
        })
    return result


# ─── Standard Scores ─────────────────────────────────────


@router.post("/standard-scores", response_model=StandardScoreResponse, status_code=status.HTTP_201_CREATED)
def create_standard_score_route(payload: StandardScoreCreate, db: Session = Depends(get_db)) -> StandardScoreResponse:
    data = payload.model_dump()
    score = repo_create_standard_score(db, data)
    db.commit()
    db.refresh(score)
    return StandardScoreResponse.model_validate(score)


@router.get("/standard-scores", response_model=list[StandardScoreResponse])
def list_standard_scores_route(
    scope_type: str | None = Query(default=None),
    scope_id: str | None = Query(default=None),
    metric_type: str | None = Query(default=None),
    period: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[StandardScoreResponse]:
    scores = repo_list_standard_scores(db, scope_type=scope_type, scope_id=scope_id, metric_type=metric_type, period=period)
    return [StandardScoreResponse.model_validate(s) for s in scores]


# ─── Sub-tasks ──────────────────────────────────────────────────────────


@router.post(
    "/tasks/{task_id}/subtasks",
    response_model=SubTaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_sub_task_route(
    task_id: int, payload: SubTaskCreate, db: Session = Depends(get_db)
) -> SubTaskResponse:
    row = create_sub_task_for_task(db, task_id=task_id, payload=payload.model_dump())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    return SubTaskResponse.model_validate(row)


@router.get("/tasks/{task_id}/subtasks", response_model=list[SubTaskResponse])
def list_sub_tasks_route(
    task_id: int, db: Session = Depends(get_db)
) -> list[SubTaskResponse]:
    rows = list_sub_tasks(db, task_id)
    if rows is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    return [SubTaskResponse.model_validate(r) for r in rows]


@router.patch("/subtasks/{sub_task_id}", response_model=SubTaskResponse)
def update_sub_task_route(
    sub_task_id: int, payload: SubTaskUpdate, db: Session = Depends(get_db)
) -> SubTaskResponse:
    row = update_sub_task_by_id(db, sub_task_id, payload.model_dump(exclude_unset=True))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sub-task not found")
    return SubTaskResponse.model_validate(row)


@router.delete("/subtasks/{sub_task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sub_task_route(sub_task_id: int, db: Session = Depends(get_db)) -> None:
    ok = delete_sub_task_by_id(db, sub_task_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sub-task not found")


@router.post(
    "/tasks/{task_id}/subtasks/generate",
    response_model=SubTaskGeneratePreviewResponse,
)
@limiter.limit(lambda: get_settings().rate_limit_recommendation)
def generate_sub_tasks_preview_route(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db),
) -> SubTaskGeneratePreviewResponse:
    drafts = generate_sub_tasks_preview(db, task_id=task_id)
    if drafts is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    return SubTaskGeneratePreviewResponse(task_id=task_id, drafts=drafts)


# ─── Obstacles ─────────────────────────────────────────────────────────


@router.post(
    "/tasks/{task_id}/obstacles",
    response_model=ObstacleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_obstacle_route(
    task_id: int, payload: ObstacleCreate, db: Session = Depends(get_db)
) -> ObstacleResponse:
    row = create_obstacle_for_task(db, task_id=task_id, payload=payload.model_dump())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    return ObstacleResponse.model_validate(row)


@router.get("/tasks/{task_id}/obstacles", response_model=list[ObstacleResponse])
def list_obstacles_route(
    task_id: int, db: Session = Depends(get_db)
) -> list[ObstacleResponse]:
    rows = list_obstacles(db, task_id)
    if rows is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    return [ObstacleResponse.model_validate(r) for r in rows]


@router.patch("/obstacles/{obstacle_id}", response_model=ObstacleResponse)
def update_obstacle_route(
    obstacle_id: int, payload: ObstacleUpdate, db: Session = Depends(get_db)
) -> ObstacleResponse:
    row = update_obstacle_by_id(db, obstacle_id, payload.model_dump(exclude_unset=True))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="obstacle not found")
    return ObstacleResponse.model_validate(row)


@router.post("/obstacles/{obstacle_id}/analyze", response_model=ObstacleResponse)
@limiter.limit(lambda: get_settings().rate_limit_recommendation)
def analyze_obstacle_route(
    request: Request,
    obstacle_id: int,
    db: Session = Depends(get_db),
) -> ObstacleResponse:
    row = analyze_obstacle_by_id(db, obstacle_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="obstacle not found")
    return ObstacleResponse.model_validate(row)


@router.post("/obstacles/{obstacle_id}/resolve", response_model=ObstacleResponse)
def resolve_obstacle_route(
    obstacle_id: int,
    payload: ObstacleResolveRequest,
    db: Session = Depends(get_db),
) -> ObstacleResponse:
    row = resolve_obstacle_by_id(db, obstacle_id, resolution_notes=payload.resolution_notes)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="obstacle not found")
    return ObstacleResponse.model_validate(row)
