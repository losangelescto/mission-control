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
    subtasks: Sequence[dict] | None = None,
    active_obstacles: Sequence[dict] | None = None,
    resolved_obstacles: Sequence[dict] | None = None,
) -> str:
    """Return the full system prompt for a standard recommendation call.

    Section order is deliberate: the "live operational state" cluster
    (current blocker → active obstacles → recently resolved obstacles)
    sits next to updates so the LLM treats resolutions as continuity
    context, not appendix data. Reviews/history/subtasks follow as
    supporting structure.
    """
    sections = [
        _SHARED_VOICE,
        _STANDARD_INSTRUCTIONS,
        _format_seven_standards(),
        _format_retrieved_chunks(canon_chunks),
        _format_updates(updates),
        _format_blocker(blocker),
        format_active_obstacles(active_obstacles or []),
        format_resolved_obstacles(resolved_obstacles or []),
        _format_reviews(reviews),
        _format_history_summary(history_summary),
        format_subtask_progress(subtasks or []),
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
    subtasks: Sequence[dict] | None = None,
    active_obstacles: Sequence[dict] | None = None,
    resolved_obstacles: Sequence[dict] | None = None,
) -> str:
    """Return the full system prompt for an unblock-mode call.

    Same live-operational-state ordering as standard mode so the
    unblock alternatives can build on (or distinguish from) recently
    resolved obstacles.
    """
    sections = [
        _SHARED_VOICE,
        _UNBLOCK_INSTRUCTIONS,
        _format_seven_standards(),
        _format_retrieved_chunks(canon_chunks),
        _format_updates(updates),
        _format_blocker(blocker),
        format_active_obstacles(active_obstacles or []),
        format_resolved_obstacles(resolved_obstacles or []),
        _format_reviews(reviews),
        _format_history_summary(history_summary),
        format_subtask_progress(subtasks or []),
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


# ─── Sub-task generation ────────────────────────────────────────────────


_SUBTASK_INSTRUCTIONS = """SUB-TASK GENERATION MODE:

Break the task below into 3-7 concrete action steps. Each step must:
- Be a specific action the owner can execute, not a vague intention.
- Align to a single Standard from The Uncommon Pursuit (see below).
- State what "done" looks like in the description.

Output schema — return a JSON object with EXACTLY this key:
  "subtasks": JSON array of 3-7 objects, each with:
    "title":             one short action-oriented sentence
    "description":       what to do, why it matters, and what "done" looks like
    "canon_reference":   the Standard this step serves, by name (one of the Seven)
"""


def build_subtask_system_prompt(canon_chunks: Sequence[dict]) -> str:
    sections = [
        _SHARED_VOICE,
        _SUBTASK_INSTRUCTIONS,
        _format_seven_standards(),
        _format_retrieved_chunks(canon_chunks),
    ]
    return "\n\n---\n\n".join(sections)


def build_subtask_user_message(*, task: dict) -> str:
    return (
        _format_task_header(task)
        + "\n\n"
        + f"Description:\n{task.get('description', '').strip()}\n"
        + "\n"
        + "Produce the sub-task JSON now."
    )


# ─── Obstacle analysis (reuses unblock instructions for consistency) ────


_OBSTACLE_INSTRUCTIONS = """OBSTACLE ANALYSIS MODE:

A specific obstacle is described below. Generate EXACTLY three first-principles
alternatives for moving past it. Each alternative must be distinct in approach,
not a variation on the same idea.

Output schema — return a JSON object with EXACTLY these keys:
  "blocker_summary":      one or two sentences describing the obstacle
  "root_cause_analysis":  3-5 sentences identifying the root cause
  "alternatives":         JSON array of EXACTLY 3 objects, each with:
                            "path"              — short name of the alternative
                            "solves"            — what this alternative resolves
                            "tradeoff"          — what it costs or risks
                            "first_step"        — concrete first step
                            "aligned_standard"  — one of the Seven Standards
  "recommended_path":     one sentence of the form "Path <name> because <reason>"
  "canon_reference":      one to two sentences citing the canon
"""


_EXTRACTION_INSTRUCTIONS = """TASK-EXTRACTION MODE INSTRUCTIONS:

You are turning raw operational source material (emails, transcripts, call \
artifacts, board exports) into discrete actionable candidates. Be honest about \
confidence: most lines in a real source are discussion, not action items.

Distinguish three kinds of candidate, and set ``confidence`` accordingly:
- ``action_item``  — someone explicitly committed to doing something. \
Confidence >= 0.75.
- ``decision``     — a choice was made on the call but no one was named to \
execute. Confidence around 0.55-0.7.
- ``discussion``   — a topic was raised but no commitment or decision. \
Confidence <= 0.5.

Other rules:
- ``suggested_owner`` should use the speaker label or named person from the \
text when one is identifiable; otherwise null.
- ``suggested_priority`` is one of "low", "medium", "high" — read urgency \
language from the text, not assumptions.
- ``suggested_due_date`` is an ISO-8601 date string when a real date is \
mentioned; null otherwise. Do NOT invent due dates.
- ``source_reference`` is a short anchor (3-8 words) so the operator can find \
the moment in the recording or document.
- ``source_timestamp`` is "MM:SS → MM:SS" for transcripts when segment \
boundaries are available; null for non-transcript sources.
- ``canon_alignment`` is the single most relevant Standard from the seven \
listed below.

Output schema — return a JSON object with EXACTLY one key:
  "candidates": JSON array (may be empty), each entry an object with:
    "title"               — <= 100 characters, one specific action or topic
    "description"         — 1-3 sentences with the gist + any commitment
    "suggested_owner"     — string or null
    "suggested_priority"  — "low" | "medium" | "high"
    "suggested_due_date"  — ISO date string ("YYYY-MM-DD") or null
    "source_reference"    — short anchor phrase
    "source_timestamp"    — "MM:SS → MM:SS" or null
    "confidence"          — float in [0.0, 1.0]
    "canon_alignment"     — one of the Seven Standards by name
    "extraction_kind"     — "action_item" | "decision" | "discussion"
"""


_CANON_CHANGE_INSTRUCTIONS = """CANON-CHANGE ANALYSIS MODE INSTRUCTIONS:

You will be given two versions of a canon document — VERSION 1 (PREVIOUS) and \
VERSION 2 (CURRENT, just activated) — plus a unified diff and the list of \
currently-active tasks. Your job is to explain — concretely — what operators \
should re-check.

VERSION 2 has different content from VERSION 1 but is NOT empty. Describe the \
change as a MODIFICATION between two valid policies. NEVER describe VERSION 2 \
as "deleted", "removed", "empty", "cleared", or "missing" unless VERSION 2 \
literally contains no text. The diff format may show deletion+insertion blocks; \
read those as one substitution, not as a removal.

Focus on what VERSION 2 ADDS, REMOVES, or CHANGES relative to VERSION 1. \
Do NOT say "review your tasks". Name the actual change in the canon, then name \
which kinds of in-flight work are most likely to be out-of-date because of it.

Output schema — return a JSON object with EXACTLY these keys:
  "change_summary":        2-4 sentences describing what materially changed
  "impact_analysis":       3-6 sentences describing how the change affects \
in-flight work, naming task patterns where possible
  "affected_task_titles":  JSON array of task titles (subset of the list \
provided) that are most likely affected; may be empty
"""


def build_extraction_system_prompt(
    *,
    source_kind: str,
    has_speakers: bool,
    has_timestamps: bool,
    canon_chunks: Sequence[dict] | None = None,
) -> str:
    """Prompt for extracting task candidates from a single source segment.

    ``source_kind`` is a free-form descriptor like "email thread", "call
    transcript", "board export"; it is woven into the preamble so the LLM
    knows what shape of input to expect.
    """
    intro_lines: list[str] = [f"You are processing a {source_kind}."]
    if has_speakers:
        intro_lines.append(
            "The text includes speaker labels in `[Speaker N]` form — use "
            "them to infer ownership when someone explicitly commits."
        )
    if has_timestamps:
        intro_lines.append(
            "Segment timestamps are available; use them when populating "
            "`source_timestamp`."
        )
    intro = " ".join(intro_lines)

    sections = [
        _SHARED_VOICE,
        intro,
        _EXTRACTION_INSTRUCTIONS,
        _format_seven_standards(),
    ]
    if canon_chunks:
        sections.append(_format_retrieved_chunks(canon_chunks))
    return "\n\n---\n\n".join(s for s in sections if s)


def build_extraction_user_message(
    *,
    source_filename: str,
    source_text: str,
    window_label: str | None = None,
) -> str:
    header = f"Source: {source_filename}"
    if window_label:
        header += f" — segment {window_label}"
    body = source_text.strip() or "(empty source)"
    return f"{header}\n\n{body}\n\nProduce the candidates JSON now."


def build_dedup_system_prompt() -> str:
    return "\n\n---\n\n".join(
        [
            _SHARED_VOICE,
            (
                "DEDUPLICATION MODE INSTRUCTIONS:\n\n"
                "Given multiple candidate-task lists drawn from different segments "
                "of the same recording, merge duplicates: same action item, same "
                "owner, same intent. Prefer the most complete description and the "
                "earliest source_timestamp. Keep the highest confidence value of "
                "the duplicates.\n\n"
                "Output schema: return the same JSON object shape as extraction "
                'mode — `{"candidates": [...]}` — with duplicates collapsed.'
            ),
        ]
    )


def build_dedup_user_message(grouped_candidates: list[list[dict]]) -> str:
    import json

    serialised = json.dumps({"groups": grouped_candidates}, ensure_ascii=False, indent=2)
    return (
        "Below are candidate lists per window. Merge duplicates and return "
        "the unified candidates JSON.\n\n" + serialised
    )


def build_canon_change_system_prompt(*, canon_doc_label: str) -> str:
    intro = (
        f"You are analysing a new version of the canon document `{canon_doc_label}` "
        "against the previous active version."
    )
    return "\n\n---\n\n".join(
        [
            _SHARED_VOICE,
            intro,
            _CANON_CHANGE_INSTRUCTIONS,
            _format_seven_standards(),
        ]
    )


_CANON_TEXT_PREVIEW_MAX = 4000


def _preview_canon_text(text: str, label: str) -> str:
    """Trim a canon body for the LLM prompt while keeping enough signal to
    describe modifications. Truncation is honest — we mark it explicitly so
    the LLM doesn't infer "the rest was deleted"."""
    body = text or ""
    if not body.strip():
        return f"{label} (EMPTY DOCUMENT)"
    if len(body) <= _CANON_TEXT_PREVIEW_MAX:
        return f"{label}:\n{body}"
    return (
        f"{label} (first {_CANON_TEXT_PREVIEW_MAX} chars of {len(body)}):\n"
        f"{body[:_CANON_TEXT_PREVIEW_MAX]}\n…(truncated for prompt budget; full document still in force)"
    )


def build_canon_change_user_message(
    *,
    diff_text: str,
    active_task_titles: Sequence[str],
    previous_text: str = "",
    new_text: str = "",
) -> str:
    titles_block = "\n".join(f"- {t}" for t in active_task_titles) or "(none)"
    previous_block = _preview_canon_text(previous_text, "VERSION 1 (PREVIOUS)")
    new_block = _preview_canon_text(new_text, "VERSION 2 (CURRENT)")
    return (
        f"{previous_block}\n\n"
        f"{new_block}\n\n"
        "Unified diff between the two versions:\n\n"
        f"{diff_text or '(no textual diff produced)'}\n\n"
        "Currently-active task titles:\n"
        f"{titles_block}\n\n"
        "Produce the canon-change-analysis JSON now."
    )


def build_obstacle_system_prompt(canon_chunks: Sequence[dict]) -> str:
    sections = [
        _SHARED_VOICE,
        _OBSTACLE_INSTRUCTIONS,
        _format_seven_standards(),
        _format_retrieved_chunks(canon_chunks),
    ]
    return "\n\n---\n\n".join(sections)


def build_obstacle_user_message(*, task: dict, obstacle_description: str, obstacle_impact: str) -> str:
    return (
        _format_task_header(task)
        + "\n\n"
        + f"Obstacle description: {obstacle_description.strip()}\n"
        + f"Obstacle impact: {obstacle_impact.strip() or '(not specified)'}\n"
        + "\n"
        + "Produce the obstacle-analysis JSON now."
    )


# ─── Recommendation extras: sub-task progress + active obstacles ────────


def format_subtask_progress(subtasks: Sequence[dict]) -> str:
    if not subtasks:
        return "Sub-tasks: (none defined)"
    total = len(subtasks)
    completed = sum(1 for s in subtasks if s.get("status") == "completed")
    in_progress = sum(1 for s in subtasks if s.get("status") == "in_progress")
    header = f"Sub-tasks: {completed} of {total} completed ({in_progress} in progress)"
    lines = [header]
    for s in subtasks[:10]:
        status = s.get("status", "pending")
        title = (s.get("title") or "").strip()
        ref = (s.get("canon_reference") or "").strip()
        ref_part = f" [aligned: {ref}]" if ref else ""
        lines.append(f"  - [{status}] {title}{ref_part}")
    return "\n".join(lines)


def format_active_obstacles(obstacles: Sequence[dict]) -> str:
    if not obstacles:
        return "Active obstacles: none"
    lines = [f"Active obstacles ({len(obstacles)}):"]
    for o in obstacles:
        desc = (o.get("description") or "").strip()
        impact = (o.get("impact") or "").strip()
        proposals = o.get("proposed_solutions") or []
        lines.append(f"  - {desc}")
        if impact:
            lines.append(f"      impact: {impact}")
        if proposals:
            lines.append(
                f"      {len(proposals)} proposed solution(s) already generated — "
                f"build on them rather than duplicate."
            )
    return "\n".join(lines)


RESOLUTION_CITATION_INSTRUCTION = (
    "When reasoning about next actions, reference recent resolutions explicitly when "
    "they're relevant to the current task state — the resident or team should see "
    "continuity between problems already solved and what comes next. Quote or paraphrase "
    "the resolution narrative below when it changes how you'd plan the next move."
)


def format_resolved_obstacles(obstacles: Sequence[dict]) -> str:
    """Format recently-resolved obstacles so the LLM can build on what just got unstuck.

    Each obstacle dict is expected to carry ``description``, ``impact``,
    ``resolution_notes``, and ``resolved_ago_days`` (an integer). When no
    obstacles are passed, returns an empty string so the section is dropped
    from the prompt entirely.
    """
    if not obstacles:
        return ""
    lines = [
        "Recently resolved obstacles (cite the resolution narrative when planning, "
        "especially the resolution_notes — these are recent wins the resident/team "
        "has already delivered):",
    ]
    for i, o in enumerate(obstacles, start=1):
        desc = (o.get("description") or "").strip() or "(no description)"
        impact = (o.get("impact") or "").strip()
        notes = (o.get("resolution_notes") or "").strip()
        ago_days = o.get("resolved_ago_days")
        ago_label = (
            f"resolved {ago_days} day{'s' if ago_days != 1 else ''} ago"
            if isinstance(ago_days, int)
            else "recently resolved"
        )
        lines.append(f"{i}. Obstacle: {desc}")
        if impact:
            lines.append(f"   Impact: {impact}")
        lines.append(
            f"   How it was resolved: {notes if notes else '(no resolution notes recorded)'}"
        )
        lines.append(f"   Resolved: {ago_label}")
    lines.append(RESOLUTION_CITATION_INSTRUCTION)
    return "\n".join(lines)


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
