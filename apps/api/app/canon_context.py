"""Assemble the canon-grounded system prompt for recommendation generation.

Two modes:

- **Standard** (``build_standard_system_prompt``/``build_standard_user_message``):
  every not-blocked task. Includes canon chunks, Seven Standards reference
  frame, the task's recent updates, its review notes, and a history summary
  so the LLM can reference what has already been tried.

- **Unblock** (``build_unblock_system_prompt``/``build_unblock_user_message``):
  used when ``task.status == "blocked"``. The prompt asks for root-cause
  analysis and three first-principles alternatives with trade-offs, each
  aligned to a Standard.

Both modes share the same voice: direct, conviction-driven, no corporate
filler. Both require strict-JSON output to a schema the provider will
parse.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence


SEVEN_STANDARDS: list[tuple[str, str]] = [
    ("Anticipation", "Seeing what's needed before it's asked."),
    ("Recognition", "Acknowledging effort, presence, and contribution."),
    ("Consistency", "Delivering the same standard every time."),
    ("Accountability", "Owning outcomes, not just tasks."),
    ("Emotional Intelligence", "Reading the room and responding with care."),
    ("Ownership", "Acting like it's yours — because it is."),
    ("Elevation", "Raising the bar, never settling."),
]


# ─── Shared voice preamble ──────────────────────────────────────────────

_SHARED_VOICE = """You are the operational intelligence for The Uncommon Pursuit, \
the operating philosophy for luxury property management.

The voice is direct, conviction-driven, and exacting — no corporate filler, no \
"consider", no "evaluate". Name the move. Name the Standard it serves. Give a \
concrete action the owner can execute today.

You MUST return a single JSON object and nothing else — no prose before or \
after, no markdown fences. The schema for this mode is spelled out below; \
follow it exactly."""


# ─── Standard mode ──────────────────────────────────────────────────────

_STANDARD_INSTRUCTIONS = """STANDARD MODE INSTRUCTIONS:

Every recommendation must:
- Lead with the single Standard most at stake for this task.
- Frame the objective in terms of The Uncommon Pursuit's mission, not generic \
project management.
- Incorporate the update history below: what has changed, what progress has \
been made, what keeps recurring. If the same blocker or concern appears \
multiple times, flag it as a pattern.
- Build on what has already been tried. Do NOT repeat advice that prior \
updates show was already attempted.
- Reference specific updates inline when relevant \
(for example: "Based on the Apr 10 update where...").
- End with a single next_action specific enough to execute today.

Output schema — return a JSON object with EXACTLY these keys:
  "standard":              one of the Seven Standards by name
  "objective":             one sentence, mission-aligned
  "first_principles_plan": 3-5 sentences grounded in the canon, not templates
  "viable_options":        JSON array of 2-3 strings, each a distinct option with its trade-off
  "next_action":           one concrete action the owner can execute today
"""


# ─── Unblock mode ───────────────────────────────────────────────────────

_UNBLOCK_INSTRUCTIONS = """UNBLOCK MODE INSTRUCTIONS:

This task is blocked. Your job is to break the block with first-principles \
thinking, not to repeat what has already been tried.

Do all of the following:
- Acknowledge the specific blocker described below.
- Perform root-cause analysis: name the root cause, not the symptom.
- Propose EXACTLY THREE alternative paths forward. Each alternative must be \
distinct in approach — not three variations of the same idea.
- For each alternative, align it to the single most relevant of the Seven \
Standards.
- End with a recommended_path stating which alternative you choose and why, \
in terms of the canon.

Output schema — return a JSON object with EXACTLY these keys:
  "blocker_summary":      one or two sentences describing what is blocking the task
  "root_cause_analysis":  3-5 sentences identifying the root cause (not the symptom)
  "alternatives":         JSON array of EXACTLY 3 objects, each with:
                            "path"              — short name of the alternative
                            "solves"            — what this alternative resolves
                            "tradeoff"          — what it costs or risks
                            "first_step"        — a concrete first step to execute
                            "aligned_standard"  — one of the Seven Standards by name
  "recommended_path":     one sentence of the form "Path <name> because <reason>"
  "canon_reference":      one to two sentences quoting or paraphrasing the canon excerpt that supports the recommended path
"""


# ─── Formatters ─────────────────────────────────────────────────────────

def _format_seven_standards() -> str:
    lines = ["The Seven Standards (always apply all seven; pick the one most at stake):"]
    for name, description in SEVEN_STANDARDS:
        lines.append(f"  - {name}: {description}")
    return "\n".join(lines)


def _format_retrieved_chunks(chunks: Sequence[dict]) -> str:
    if not chunks:
        return "No canon or source excerpts retrieved for this task."

    blocks: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        source = chunk.get("source_filename") or f"source_{chunk.get('source_document_id', '?')}"
        is_canon = bool(chunk.get("is_active_canon_version"))
        label = "CANON" if is_canon else "HISTORY"
        text = (chunk.get("chunk_text") or "").strip()
        blocks.append(f"[{label} #{i}] {source}\n{text}")
    return "Retrieved excerpts (ranked by relevance):\n\n" + "\n\n".join(blocks)


def _format_updates(updates: Sequence[dict]) -> str:
    if not updates:
        return "Task update history: (no updates recorded yet)"
    lines = ["Task update history (newest first — reference these when relevant):"]
    for upd in updates:
        ts = upd.get("created_at_display") or upd.get("created_at") or "?"
        author = upd.get("created_by") or "unknown"
        summary = (upd.get("summary") or "").strip()
        lines.append(f"  - [{ts}] {author}: {summary}")
    return "\n".join(lines)


def _format_blocker(blocker: dict | None) -> str:
    if not blocker:
        return "Current blocker: none — task is not blocked."
    opened = blocker.get("opened_at_display") or blocker.get("opened_at") or "?"
    reason = (blocker.get("blocker_reason") or "").strip()
    severity = blocker.get("severity") or "?"
    btype = blocker.get("blocker_type") or "?"
    return (
        f"Current blocker (opened {opened}):\n"
        f"  type: {btype}\n"
        f"  severity: {severity}\n"
        f"  reason: {reason}"
    )


def _format_reviews(reviews: Sequence[dict]) -> str:
    if not reviews:
        return "Recent review sessions: (none)"
    lines = ["Recent review sessions (newest first):"]
    for r in reviews:
        ts = r.get("created_at_display") or r.get("created_at") or "?"
        reviewer = r.get("reviewer") or "unknown"
        notes = (r.get("notes") or "").strip()
        action_items = (r.get("action_items") or "").strip()
        lines.append(f"  - [{ts}] {reviewer}")
        if notes:
            lines.append(f"      notes: {notes}")
        if action_items:
            lines.append(f"      action_items: {action_items}")
    return "\n".join(lines)


def _format_history_summary(summary: dict | None) -> str:
    if not summary:
        return ""
    parts = [
        f"days since creation: {summary.get('days_since_creation', '?')}",
        f"updates recorded: {summary.get('update_count', 0)}",
        f"times blocked: {summary.get('block_count', 0)}",
        f"reassignments: {summary.get('reassignment_count', 0)}",
    ]
    return "Task history summary: " + " | ".join(parts)


def _format_task_header(task: dict) -> str:
    due_line = task.get("due_at_display") or task.get("due_at") or "not set"
    return (
        f"Task: {task.get('title', '').strip()}\n"
        f"Status: {task.get('status')} | Priority: {task.get('priority')}\n"
        f"Owner: {task.get('owner_name')} | Assigned by: {task.get('assigner_name')}\n"
        f"Due: {due_line}"
    )


# ─── Public builders — standard mode ────────────────────────────────────

def build_standard_system_prompt(
    *,
    canon_chunks: Sequence[dict],
    updates: Sequence[dict],
    blocker: dict | None,
    reviews: Sequence[dict],
    history_summary: dict | None,
) -> str:
    """Return the full system prompt for a standard recommendation call."""
    sections = [
        _SHARED_VOICE,
        _STANDARD_INSTRUCTIONS,
        _format_seven_standards(),
        _format_retrieved_chunks(canon_chunks),
        _format_updates(updates),
        _format_blocker(blocker),
        _format_reviews(reviews),
        _format_history_summary(history_summary),
    ]
    return "\n\n---\n\n".join(s for s in sections if s)


def build_standard_user_message(
    *,
    task: dict,
    objective_seed: str,
    standard_seed: str,
) -> str:
    return (
        _format_task_header(task)
        + "\n\n"
        + f"Current objective (may be refined): {objective_seed}\n"
        + f"Current standard hint (may be refined): {standard_seed}\n"
        + "\n"
        + f"Description:\n{task.get('description', '').strip()}\n"
        + "\n"
        + "Produce the standard-mode JSON recommendation now."
    )


# ─── Public builders — unblock mode ─────────────────────────────────────

def build_unblock_system_prompt(
    *,
    canon_chunks: Sequence[dict],
    updates: Sequence[dict],
    blocker: dict | None,
    reviews: Sequence[dict],
    history_summary: dict | None,
) -> str:
    """Return the full system prompt for an unblock-mode call."""
    sections = [
        _SHARED_VOICE,
        _UNBLOCK_INSTRUCTIONS,
        _format_seven_standards(),
        _format_retrieved_chunks(canon_chunks),
        _format_updates(updates),
        _format_blocker(blocker),
        _format_reviews(reviews),
        _format_history_summary(history_summary),
    ]
    return "\n\n---\n\n".join(s for s in sections if s)


def build_unblock_user_message(*, task: dict) -> str:
    return (
        _format_task_header(task)
        + "\n\n"
        + f"Description:\n{task.get('description', '').strip()}\n"
        + "\n"
        + "Produce the unblock-mode JSON recommendation now. Three distinct "
        + "alternatives are required — not three variations of the same idea."
    )


# ─── Helpers used by services to normalise timestamps for display ───────

def format_timestamp(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d")


def serialize_for_context(value: Any) -> Any:
    """Best-effort JSON-friendly conversion used by the context hash."""
    if isinstance(value, datetime):
        return value.isoformat()
    return value
