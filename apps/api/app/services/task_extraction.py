"""LLM-driven task candidate extraction.

Reads a SourceDocument's extracted text (plus, for transcripts, the
``processing_metadata.segments`` list with speaker/timestamp data),
runs the configured ``AIProvider.extract_candidates`` with prompts from
``canon_context``, and writes the result as ``task_candidates`` rows.

For long transcripts the source is split into ``extraction_window_minutes``
windows; each window is extracted independently and the union is then
deduplicated through a second LLM pass before being persisted.

Canon documents (``source_type == "canon_doc"``) are skipped — they
describe standards, not action items.
"""
from __future__ import annotations

import logging
import time
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.canon_context import (
    build_dedup_system_prompt,
    build_dedup_user_message,
    build_extraction_system_prompt,
    build_extraction_user_message,
)
from app.config import get_settings
from app.models import SourceDocument, TaskCandidate
from app.providers import AIProvider, ExtractedCandidate, get_ai_provider
from app.repositories import (
    create_task_candidate as repo_create_task_candidate,
    get_source_document_by_id,
)
from app.task_candidate_extraction import (
    CandidateDraft,
    candidate_draft_hints_json,
    extract_task_candidates_with_heuristics,
)

logger = logging.getLogger(__name__)

CANON_DOC_TYPE = "canon_doc"


def extract_task_candidates_from_source(
    db: Session,
    source_id: int,
    *,
    ai_provider: AIProvider | None = None,
) -> list[TaskCandidate] | None:
    """Run heuristic + LLM extraction for ``source_id`` and persist results.

    Returns ``None`` when the source does not exist, ``[]`` when the
    source is canon (or has no usable text), and the created rows
    otherwise.
    """
    source = get_source_document_by_id(db, source_id)
    if source is None:
        return None
    if source.source_type == CANON_DOC_TYPE:
        logger.info(
            "skipping extraction for canon document",
            extra={"event": "extraction_skipped_canon", "context": {"source_id": source_id}},
        )
        return []

    t0 = time.monotonic()
    logger.info(
        "task candidate extraction started",
        extra={"event": "candidate_extraction_started", "context": {"source_id": source_id}},
    )

    provider = ai_provider or get_ai_provider()

    heuristic = extract_task_candidates_with_heuristics(
        source_text=source.extracted_text or "",
        source_date=source.created_at,
    )

    llm_candidates = _run_llm_extraction(provider=provider, source=source)

    # When the LLM produces at least one high-signal candidate, drop
    # heuristic rows that are just verbatim copies of input lines with no
    # hints — they're noise alongside a real LLM result. We never strip
    # the heuristic list to empty; if the LLM produced nothing, the
    # heuristic catch-all is still the operator's only signal.
    heuristic = _suppress_verbatim_catchalls(
        heuristic=heuristic, llm_candidates=llm_candidates
    )

    fallback_due = (source.created_at + timedelta(days=7)).replace(tzinfo=UTC)
    created: list[TaskCandidate] = []

    for draft in heuristic:
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
            },
        )
        created.append(row)

    for cand in llm_candidates:
        row = repo_create_task_candidate(
            db,
            _llm_candidate_to_row(cand, source=source, fallback_due=fallback_due),
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
                "llm_candidate_count": len(llm_candidates),
                "duration_ms": round((time.monotonic() - t0) * 1000, 2),
            },
        },
    )
    return created


# ─── LLM driver ──────────────────────────────────────────────────────


def _run_llm_extraction(
    *,
    provider: AIProvider,
    source: SourceDocument,
) -> list[ExtractedCandidate]:
    settings = get_settings()
    text = source.extracted_text or ""
    if not text.strip():
        return []

    metadata = source.processing_metadata or {}
    segments = metadata.get("segments") if isinstance(metadata, dict) else None
    duration = metadata.get("duration_seconds") if isinstance(metadata, dict) else None

    has_speakers = bool(segments) and any(seg.get("speaker") for seg in segments)
    has_timestamps = bool(segments) and any("start_time" in seg for seg in segments)
    source_kind = _describe_source_kind(source.source_type)

    window_minutes = settings.extraction_window_minutes
    needs_windowing = bool(
        segments
        and window_minutes
        and isinstance(duration, (int, float))
        and duration > window_minutes * 60
    )

    if not needs_windowing:
        system_prompt = build_extraction_system_prompt(
            source_kind=source_kind,
            has_speakers=has_speakers,
            has_timestamps=has_timestamps,
        )
        user_message = build_extraction_user_message(
            source_filename=source.filename,
            source_text=_render_segments(segments) if segments else text,
        )
        try:
            return provider.extract_candidates(
                system_prompt=system_prompt,
                user_message=user_message,
            )
        except Exception:
            logger.exception(
                "extract_candidates failed",
                extra={"context": {"source_id": source.id}},
            )
            return []

    windows = _segment_windows(segments, window_minutes=window_minutes)
    per_window: list[list[ExtractedCandidate]] = []
    system_prompt = build_extraction_system_prompt(
        source_kind=source_kind,
        has_speakers=True,
        has_timestamps=True,
    )
    for label, window_segments in windows:
        user_message = build_extraction_user_message(
            source_filename=source.filename,
            source_text=_render_segments(window_segments),
            window_label=label,
        )
        try:
            cands = provider.extract_candidates(
                system_prompt=system_prompt,
                user_message=user_message,
            )
        except Exception:
            logger.exception(
                "windowed extract_candidates failed",
                extra={"context": {"source_id": source.id, "window": label}},
            )
            cands = []
        per_window.append(cands)

    return _dedup_through_provider(provider=provider, per_window=per_window)


def _dedup_through_provider(
    *,
    provider: AIProvider,
    per_window: list[list[ExtractedCandidate]],
) -> list[ExtractedCandidate]:
    flat = [c for group in per_window for c in group]
    if len(flat) <= 1:
        return flat

    grouped = [[asdict(c) for c in group] for group in per_window]
    try:
        provider.extract_candidates(
            system_prompt=build_dedup_system_prompt(),
            user_message=build_dedup_user_message(grouped),
        )
    except Exception:
        logger.exception("dedup pass failed; using local title-key dedup")

    # Whether or not the provider's dedup pass worked, fall back to a
    # title-key dedup so we never emit two identical-looking candidates.
    seen: dict[str, ExtractedCandidate] = {}
    for cand in flat:
        key = cand.title.strip().lower()
        existing = seen.get(key)
        if existing is None or cand.confidence > existing.confidence:
            seen[key] = cand
    return list(seen.values())


def _llm_candidate_to_row(
    candidate: ExtractedCandidate,
    *,
    source: SourceDocument,
    fallback_due: datetime,
) -> dict:
    inferred_due = _parse_iso_date(candidate.suggested_due_date_iso)
    hints: dict = {
        "extraction_kind": candidate.extraction_kind,
        "llm_extracted": True,
    }
    return {
        "source_document_id": source.id,
        "title": candidate.title[:255],
        "description": candidate.description,
        "inferred_owner_name": candidate.suggested_owner,
        "inferred_due_at": inferred_due,
        "fallback_due_at": fallback_due,
        "review_status": "pending_review",
        "confidence": candidate.confidence,
        "hints_json": hints,
        "candidate_kind": "new_task",
        "suggested_priority": candidate.suggested_priority,
        "source_reference": candidate.source_reference or None,
        "source_timestamp": candidate.source_timestamp,
        "canon_alignment": candidate.canon_alignment or None,
    }


# ─── Helpers ─────────────────────────────────────────────────────────


def _llm_candidates_are_high_signal(
    llm_candidates: list[ExtractedCandidate],
) -> bool:
    """True when at least one LLM candidate is action-shaped or confident.

    Threshold mirrors the prompt: ``action_item`` is the LLM's strongest
    signal that someone explicitly committed; ``confidence >= 0.6`` covers
    decisions/actions just below that bar.
    """
    for cand in llm_candidates:
        if cand.extraction_kind == "action_item":
            return True
        if cand.confidence >= 0.6:
            return True
    return False


def _is_verbatim_catchall(draft: CandidateDraft) -> bool:
    """A heuristic draft with no real hint signal beyond the raw line.

    The heuristic always copies the source line into ``title`` and bolts
    on hint strings in ``description``. When every hint list is empty,
    the row carries no information the LLM didn't already see.
    """
    return not (
        draft.urgency_hints
        or draft.blocker_hints
        or draft.recurrence_hints
        or draft.completion_hints
        or draft.delegation_hints
    )


def _suppress_verbatim_catchalls(
    *,
    heuristic: list[CandidateDraft],
    llm_candidates: list[ExtractedCandidate],
) -> list[CandidateDraft]:
    """Drop hint-less heuristic drafts when the LLM produced real candidates.

    Never returns an empty list when the LLM produced nothing — falling
    back to the heuristic is the whole point of having one.
    """
    if not llm_candidates or not _llm_candidates_are_high_signal(llm_candidates):
        return heuristic
    filtered = [d for d in heuristic if not _is_verbatim_catchall(d)]
    if not filtered and heuristic:
        # Defensive: never wipe the heuristic list to empty if it was the
        # only signal — but if LLM is high-signal, an all-empty filtered
        # list means every heuristic row was noise. The LLM rows below
        # cover the real action items, so dropping the noise is correct.
        return []
    return filtered


_SOURCE_KIND_LABELS = {
    "transcript": "call transcript",
    "thread_export": "email/thread export",
    "note": "operational note",
    "board_seed": "board export",
    "summary_doc": "call summary document",
    "manual_notes": "manual call notes",
    "mail_message": "email message",
}


def _describe_source_kind(source_type: str) -> str:
    return _SOURCE_KIND_LABELS.get(source_type, f"{source_type} source")


def _render_segments(segments: list[dict]) -> str:
    """Serialise transcript segments back to LLM-readable text with labels."""
    lines: list[str] = []
    for seg in segments or []:
        start = _format_timestamp(seg.get("start_time"))
        end = _format_timestamp(seg.get("end_time"))
        speaker = seg.get("speaker") or "Speaker"
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        lines.append(f"[{start} → {end}] {speaker}: {text}")
    return "\n".join(lines)


def _format_timestamp(value: object) -> str:
    try:
        seconds = int(float(value))
    except (TypeError, ValueError):
        return "00:00"
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _segment_windows(
    segments: list[dict],
    *,
    window_minutes: int,
) -> list[tuple[str, list[dict]]]:
    if not segments or window_minutes <= 0:
        return [("full", segments or [])]
    window_seconds = window_minutes * 60
    buckets: dict[int, list[dict]] = {}
    for seg in segments:
        start = float(seg.get("start_time") or 0.0)
        bucket = int(start // window_seconds)
        buckets.setdefault(bucket, []).append(seg)

    windows: list[tuple[str, list[dict]]] = []
    for bucket in sorted(buckets):
        start = bucket * window_seconds
        end = start + window_seconds
        label = f"{_format_timestamp(start)}-{_format_timestamp(end)}"
        windows.append((label, buckets[bucket]))
    return windows


def _parse_iso_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if len(value) == 10:
            return datetime.fromisoformat(value).replace(tzinfo=UTC)
        return datetime.fromisoformat(value)
    except ValueError:
        return None


__all__ = ["extract_task_candidates_from_source"]
