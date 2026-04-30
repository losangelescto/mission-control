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

    diff_text = _produce_unified_diff(
        previous_source.extracted_text or "",
        new_source.extracted_text or "",
        previous_label=previous_source.version_label or "previous",
        new_label=new_source.version_label or "new",
    )

    active_tasks = list_active_tasks(db)
    title_to_id = {task.title: task.id for task in active_tasks}

    provider = ai_provider or get_ai_provider()
    canon_label = new_source.canonical_doc_id or new_source.filename
    try:
        analysis = provider.analyze_canon_change(
            system_prompt=build_canon_change_system_prompt(canon_doc_label=canon_label),
            user_message=build_canon_change_user_message(
                diff_text=diff_text,
                active_task_titles=[task.title for task in active_tasks],
                previous_text=previous_source.extracted_text or "",
                new_text=new_source.extracted_text or "",
            ),
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
        previous_text=previous_source.extracted_text or "",
        new_text=new_source.extracted_text or "",
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


_DELETION_LANGUAGE_TOKENS = ("deleted", "removed", "empty", "missing", "cleared")


def _warn_if_deletion_language_misapplied(
    *,
    change_summary: str,
    previous_text: str,
    new_text: str,
    canon_doc_id: str | None,
) -> None:
    """Observability for the LLM "v2 was deleted" failure mode.

    Both versions are non-empty when this check fires, so any deletion-style
    language in the summary is misleading. We log a warning rather than
    rewriting the summary — the LLM is the authority on tone, but the
    operator-facing message stays mostly correct via impact_analysis.
    """
    if not (previous_text.strip() and new_text.strip()):
        return  # one side is genuinely empty — deletion language may be accurate.
    summary_lower = (change_summary or "").lower()
    matched = [t for t in _DELETION_LANGUAGE_TOKENS if t in summary_lower]
    if matched:
        logger.warning(
            "canon_change_summary uses deletion language while v2 has content",
            extra={
                "event": "canon_change_summary_misleading",
                "context": {
                    "canon_doc_id": canon_doc_id,
                    "matched_tokens": matched,
                    "summary_preview": (change_summary or "")[:200],
                    "previous_text_len": len(previous_text),
                    "new_text_len": len(new_text),
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
