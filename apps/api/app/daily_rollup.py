"""
Daily operational roll-up (Phase 1: internal preview artifact; no outbound notifications).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models import Delegation, Recommendation, Task, TaskCandidate
from app.repositories import (
    list_all_delegations,
    list_all_recommendations,
    list_all_tasks,
    list_all_recurrence_occurrences,
    list_open_blockers,
    list_task_candidates,
)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _serialize_task_item(task: Task, reason: str) -> dict[str, Any]:
    due = _as_utc(task.due_at) if task.due_at else None
    return {
        "task_id": task.id,
        "title": task.title,
        "owner_name": task.owner_name,
        "status": task.status,
        "priority": task.priority,
        "due_at": due.isoformat() if due else None,
        "reason": reason,
    }


def _serialize_candidate(c: TaskCandidate) -> dict[str, Any]:
    return {
        "candidate_id": c.id,
        "title": c.title,
        "source_document_id": c.source_document_id,
        "review_status": c.review_status,
    }


def build_daily_rollup_sections(db: Session) -> tuple[dict[str, Any], datetime]:
    """
    Aggregate the same dimensions as operational review, plus stale delegations and
    recommendations on open tasks. Concise dict suitable for JSON storage.
    """
    now = datetime.now(UTC)
    tasks = list_all_tasks(db)
    open_blockers = list_open_blockers(db)
    recurrences = list_all_recurrence_occurrences(db)
    pending_candidates = list_task_candidates(db, review_status="pending_review")
    delegations = list_all_delegations(db)
    recommendations = list_all_recommendations(db)

    blocked_task_ids = {blocker.task_id for blocker in open_blockers}
    tasks_by_id: dict[int, Task] = {t.id: t for t in tasks}

    urgent: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    due_soon: list[dict[str, Any]] = []

    for task in tasks:
        if task.status == "completed":
            continue

        due_at = _as_utc(task.due_at) if task.due_at is not None else None
        is_due_soon = due_at is not None and due_at <= now + timedelta(days=2)
        is_urgent = task.priority.lower() in {"high", "urgent", "p0"} or (
            due_at is not None and due_at <= now + timedelta(days=1)
        )

        if is_urgent:
            urgent.append(_serialize_task_item(task, "high priority or near-term deadline"))
        if task.id in blocked_task_ids or task.status == "blocked":
            blocked.append(_serialize_task_item(task, "open blocker or blocked status"))
        if is_due_soon:
            due_soon.append(_serialize_task_item(task, "due within 48 hours"))

    latest_delegation_by_task: dict[int, Delegation] = {}
    for d in sorted(delegations, key=lambda x: x.id):
        latest_delegation_by_task[d.task_id] = d

    stale_delegated: list[dict[str, Any]] = []
    for d in latest_delegation_by_task.values():
        task = tasks_by_id.get(d.task_id)
        if task is None or task.status == "completed":
            continue
        delegated_at = _as_utc(d.delegated_at)
        if (now - delegated_at).days >= 7:
            stale_delegated.append(
                {
                    "delegation_id": d.id,
                    "task_id": d.task_id,
                    "title": task.title,
                    "owner_name": task.owner_name,
                    "delegated_from": d.delegated_from,
                    "delegated_to": d.delegated_to,
                    "delegated_at": delegated_at.isoformat(),
                    "reason": "latest delegation older than 7 days; task still open",
                }
            )

    recurring_due: list[dict[str, Any]] = []
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

    candidate_review = [_serialize_candidate(c) for c in pending_candidates]

    rec_latest_by_task: dict[int, Recommendation] = {}
    for r in sorted(recommendations, key=lambda x: x.id):
        task = tasks_by_id.get(r.task_id)
        if task is not None and task.status != "completed":
            rec_latest_by_task[r.task_id] = r

    recommendations_attention: list[dict[str, Any]] = []
    for task_id in sorted(rec_latest_by_task.keys()):
        rec = rec_latest_by_task[task_id]
        task = tasks_by_id[task_id]
        refs = rec.source_refs_json
        ref_preview: object
        if isinstance(refs, list) and refs:
            ref_preview = refs[:3]
        elif isinstance(refs, dict) and refs:
            ref_preview = dict(list(refs.items())[:3])
        else:
            ref_preview = refs
        recommendations_attention.append(
            {
                "recommendation_id": rec.id,
                "task_id": task.id,
                "task_title": task.title,
                "next_action": (rec.next_action[:280] + "…") if len(rec.next_action) > 280 else rec.next_action,
                "source_refs_preview": ref_preview,
            }
        )

    summary: dict[str, Any] = {
        "as_of": now.isoformat(),
        "urgent": urgent,
        "blocked": blocked,
        "due_soon": due_soon,
        "stale_delegated": stale_delegated,
        "recurring_due": recurring_due,
        "candidate_review": candidate_review,
        "recommendations_attention": recommendations_attention,
    }
    return summary, now


def format_daily_rollup_preview_text(summary: dict[str, Any], *, max_items_per_section: int = 15) -> str:
    """Concise operational text for human preview; includes task/source references."""
    lines: list[str] = []
    as_of = summary.get("as_of", "")
    lines.append(f"Daily roll-up (preview) — as of {as_of}")
    lines.append("Internal preview only — no notifications sent.")
    lines.append("")

    def section(title: str, key: str, fmt) -> None:
        items = summary.get(key) or []
        lines.append(f"## {title} ({len(items)})")
        for it in items[:max_items_per_section]:
            lines.append(fmt(it))
        if len(items) > max_items_per_section:
            lines.append(f"  … +{len(items) - max_items_per_section} more")
        lines.append("")

    section(
        "Urgent",
        "urgent",
        lambda x: f"- task #{x['task_id']} {x['title'][:80]} | owner={x['owner_name']} | due={x.get('due_at')}",
    )
    section(
        "Blocked",
        "blocked",
        lambda x: f"- task #{x['task_id']} {x['title'][:80]} | status={x['status']}",
    )
    section(
        "Due soon",
        "due_soon",
        lambda x: f"- task #{x['task_id']} {x['title'][:80]} | due={x.get('due_at')}",
    )
    section(
        "Stale delegated",
        "stale_delegated",
        lambda x: f"- task #{x['task_id']} {x['title'][:60]} | {x['delegated_from']}→{x['delegated_to']} @ {x['delegated_at']}",
    )
    section(
        "Recurring due",
        "recurring_due",
        lambda x: f"- occurrence #{x['occurrence_id']} template={x['recurrence_template_id']} task={x['task_id']} date={x['occurrence_date']}",
    )
    section(
        "Candidate review",
        "candidate_review",
        lambda x: f"- candidate #{x['candidate_id']} source={x['source_document_id']} | {x['title'][:80]}",
    )
    section(
        "Recommendations (open tasks)",
        "recommendations_attention",
        lambda x: f"- rec #{x['recommendation_id']} task #{x['task_id']} {x['task_title'][:60]} | next: {x['next_action'][:100]}",
    )

    return "\n".join(lines).strip()
