"""Canon change detection.

Triggered when a new version of a canon document is activated. Diffs the
new active version against the previous active version (if one exists),
asks the LLM to summarise + analyse the impact, and writes a
``CanonChangeEvent`` row. Active tasks whose titles are flagged in the
LLM's ``affected_task_titles`` (or whose body text references the
canonical_doc_id) are marked ``canon_update_pending=True``.
"""
from __future__ import annotations

import difflib
import logging

from sqlalchemy.orm import Session

from pathlib import Path

from app.canon_context import (
    build_canon_change_system_prompt,
    build_canon_change_user_message,
)
from app.models import CanonChangeEvent, SourceDocument, Task
from app.providers import AIProvider, get_ai_provider
from app.repositories import (
    create_canon_change_event,
    list_active_tasks,
    mark_tasks_canon_update_pending,
)

logger = logging.getLogger(__name__)

DIFF_CONTEXT_LINES = 2
DIFF_MAX_LINES = 200


def detect_canon_change(
    db: Session,
    *,
    new_source: SourceDocument,
    previous_source: SourceDocument | None,
    ai_provider: AIProvider | None = None,
) -> CanonChangeEvent | None:
    """Compute the diff, run impact analysis, and persist a change event.

    Returns ``None`` when there is no prior active version (the first
    activation of a canon document is not a change). The caller is
    responsible for committing the session — this function flushes but
    does not commit so it can be composed with the activation transaction.
    """
    if previous_source is None or new_source.id == previous_source.id:
        return None

    # The unified diff used to be passed to the LLM, but the +/- format
    # anchored the model on "things were deleted" even for substantive
    # rewrites. The change-summary prompt now passes both full versions
    # with explicit character counts instead. The diff helper is kept
    # available for future diagnostics but not invoked here.

    # The upload-time activation pipeline (services.ingest_source_upload →
    # activate_canon_source → detect_canon_change) runs synchronously on
    # the request thread, BEFORE the BackgroundTask that populates
    # extracted_text by parsing the file on disk. If we read extracted_text
    # straight off the SQLAlchemy object it'll be "" for a freshly-uploaded
    # source, the LLM gets empty bodies, and produces "v2 is empty"
    # hallucinations. Read text directly from source_path on demand to
    # close the race — the helper is the same one the pipeline uses, so
    # the eventual extracted_text written by the BG task matches.
    previous_text = _read_extracted_text(previous_source)
    new_text = _read_extracted_text(new_source)

    active_tasks = list_active_tasks(db)
    title_to_id = {task.title: task.id for task in active_tasks}

    provider = ai_provider or get_ai_provider()
    canon_label = new_source.canonical_doc_id or new_source.filename
    user_message = build_canon_change_user_message(
        active_task_titles=[task.title for task in active_tasks],
        previous_text=previous_text,
        new_text=new_text,
    )
    # Instrumentation so the structured logs prove what the LLM actually
    # received. Was previously needed because the model hallucinated
    # "v2 is empty" for non-empty replacements; if the issue ever recurs
    # this log lets us verify v2's text really made it into the prompt.
    v2_text_stripped = new_text.strip()
    logger.info(
        "change_summary_prompt_built",
        extra={
            "event": "change_summary_prompt_built",
            "context": {
                "canon_doc_id": new_source.canonical_doc_id,
                "v1_length": len(previous_text.strip()),
                "v2_length": len(v2_text_stripped),
                "v1_from_disk_fallback": (
                    not (previous_source.extracted_text or "").strip()
                    and bool(previous_text.strip())
                ),
                "v2_from_disk_fallback": (
                    not (new_source.extracted_text or "").strip()
                    and bool(v2_text_stripped)
                ),
                "prompt_length": len(user_message),
                "v2_text_present_in_prompt": (
                    bool(v2_text_stripped) and v2_text_stripped[:80] in user_message
                ),
            },
        },
    )
    try:
        analysis = provider.analyze_canon_change(
            system_prompt=build_canon_change_system_prompt(canon_doc_label=canon_label),
            user_message=user_message,
        )
    except Exception:
        logger.exception(
            "analyze_canon_change failed; persisting empty analysis",
            extra={
                "context": {
                    "new_source_id": new_source.id,
                    "previous_source_id": previous_source.id,
                }
            },
        )
        from app.providers import CanonChangeAnalysis

        analysis = CanonChangeAnalysis(
            change_summary="Diff captured but the impact analysis call failed.",
            impact_analysis="No analysis available — operators should re-read the new canon manually.",
            affected_task_titles=[],
        )

    _warn_if_deletion_language_misapplied(
        change_summary=analysis.change_summary,
        previous_text=previous_text,
        new_text=new_text,
        canon_doc_id=new_source.canonical_doc_id,
    )

    affected_task_ids = _resolve_affected_task_ids(
        analysis_titles=analysis.affected_task_titles,
        title_to_id=title_to_id,
        active_tasks=active_tasks,
        canon_doc_id=new_source.canonical_doc_id,
    )

    event = create_canon_change_event(
        db,
        {
            "canon_doc_id": new_source.canonical_doc_id or "",
            "previous_source_id": previous_source.id,
            "new_source_id": new_source.id,
            "change_summary": analysis.change_summary,
            "affected_task_ids": affected_task_ids,
            "impact_analysis": analysis.impact_analysis,
            "reviewed": False,
        },
    )
    mark_tasks_canon_update_pending(db, affected_task_ids)

    logger.info(
        "canon change event recorded",
        extra={
            "event": "canon_change_recorded",
            "context": {
                "event_id": event.id,
                "canon_doc_id": new_source.canonical_doc_id,
                "previous_source_id": previous_source.id,
                "new_source_id": new_source.id,
                "affected_task_count": len(affected_task_ids),
            },
        },
    )
    return event


def _produce_unified_diff(
    previous_text: str,
    new_text: str,
    *,
    previous_label: str,
    new_label: str,
) -> str:
    diff_lines = difflib.unified_diff(
        previous_text.splitlines(),
        new_text.splitlines(),
        fromfile=f"canon ({previous_label})",
        tofile=f"canon ({new_label})",
        n=DIFF_CONTEXT_LINES,
        lineterm="",
    )
    truncated = list(diff_lines)[:DIFF_MAX_LINES]
    if not truncated:
        return ""
    return "\n".join(truncated)


# Phrase-level detection — single-token "removed" can legitimately appear
# in a correct summary ("removed the 24-hour window"). Phrase matches catch
# the failure mode (whole-document deletion claim) without false positives.
def _read_extracted_text(source: SourceDocument) -> str:
    """Return the source's extracted text, reading from disk if the
    SQLAlchemy column hasn't been populated yet.

    Upload-time activation runs synchronously on the request thread before
    the BackgroundTask that fills extracted_text via the source pipeline.
    Falling back to the on-disk file lets change-summary detection see the
    real document on the very first activation pass; the BG task will write
    the same content into extracted_text shortly after.
    """
    cached = (source.extracted_text or "").strip()
    if cached:
        return source.extracted_text or ""
    path_str = source.source_path or ""
    if not path_str:
        return ""
    try:
        from app.source_extraction import extract_text

        return extract_text(Path(path_str))
    except Exception:
        logger.exception(
            "on-demand canon text extraction failed",
            extra={
                "context": {
                    "source_id": source.id,
                    "source_path": path_str,
                }
            },
        )
        return ""


_HALLUCINATION_PHRASES = (
    "version 2 is empty",
    "version 2 is now empty",
    "v2 is empty",
    "v2 contains no",
    "version 2 contains no",
    "completely removed",
    "completely empty",
    "totally empty",
    "literally empty",
    "no longer exists",
    "policy has been removed",
    "policy has been deleted",
    "entire policy has been removed",
    "the policy was removed",
    "total elimination",
    "represents a total elimination",
    "no longer documented",
    "all content has been removed",
    "version 2 was deleted",
    "v2 was deleted",
    "the new version is completely empty",
    "the new version is empty",
    "is now empty",
)


def _warn_if_deletion_language_misapplied(
    *,
    change_summary: str,
    previous_text: str,
    new_text: str,
    canon_doc_id: str | None,
) -> None:
    """Observability for the LLM "v2 was deleted" hallucination.

    Both versions are non-empty when this check fires, so any deletion-style
    phrasing in the summary is misleading. We log a warning rather than
    rewriting the summary — the LLM is the authority on tone, but the
    structured warning lets us measure the regression rate post-prompt-fix
    and gives a clear signal to retry with a stricter prompt in a future
    iteration. The change_event still persists; impact_analysis stays useful.
    """
    if not (previous_text.strip() and new_text.strip()):
        return  # one side is genuinely empty — deletion language may be accurate.
    summary_lower = (change_summary or "").lower()
    matched = [p for p in _HALLUCINATION_PHRASES if p in summary_lower]
    if matched:
        logger.warning(
            "canon_change_summary_hallucination_detected",
            extra={
                "event": "canon_change_summary_hallucination_detected",
                "context": {
                    "canon_doc_id": canon_doc_id,
                    "matched_phrases": matched,
                    "summary": change_summary,
                    "previous_text_len": len(previous_text),
                    "new_text_len": len(new_text),
                    "new_text_preview": (new_text or "")[:200],
                },
            },
        )


def _resolve_affected_task_ids(
    *,
    analysis_titles: list[str],
    title_to_id: dict[str, int],
    active_tasks: list[Task],
    canon_doc_id: str | None,
) -> list[int]:
    """Combine LLM-named titles with simple body-text mention matching.

    The LLM picks task titles it thinks are affected; we union that with
    any active task whose ``description`` or ``standard`` field mentions
    the canon_doc_id, so a literal reference in the task body never gets
    missed.
    """
    ids: list[int] = []
    seen: set[int] = set()
    for title in analysis_titles:
        tid = title_to_id.get(title)
        if tid is not None and tid not in seen:
            ids.append(tid)
            seen.add(tid)

    if canon_doc_id:
        needle = canon_doc_id.lower()
        for task in active_tasks:
            blob = " ".join(
                [
                    task.description or "",
                    task.standard or "",
                    task.objective or "",
                ]
            ).lower()
            if needle in blob and task.id not in seen:
                ids.append(task.id)
                seen.add(task.id)
    return ids


__all__ = ["detect_canon_change"]
