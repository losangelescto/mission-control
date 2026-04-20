"""Assemble the canon-grounded system prompt for recommendation generation.

The context block injected into every LLM call has three layers:

1. **Identity and voice** — a stable system preamble that positions the model as
   the operational intelligence for The Uncommon Pursuit, the operating philosophy
   for luxury property management. The voice is direct, conviction-driven, no
   corporate filler.

2. **Standing reference frame** — the Seven Standards and the canon's core
   operating principles. These are always included, independent of retrieval,
   because they apply to every recommendation.

3. **Retrieved canon chunks** — semantically ranked excerpts from the active
   canon documents, plus recent source history, selected by the embedding
   similarity search already in place upstream of this module.

The output is a single string suitable as the ``system`` parameter on the
Anthropic ``messages.create`` call. Keep it lean — the user message carries
the task itself.
"""
from __future__ import annotations

from typing import Sequence


SEVEN_STANDARDS: list[tuple[str, str]] = [
    ("Anticipation", "Seeing what's needed before it's asked."),
    ("Recognition", "Acknowledging effort, presence, and contribution."),
    ("Consistency", "Delivering the same standard every time."),
    ("Accountability", "Owning outcomes, not just tasks."),
    ("Emotional Intelligence", "Reading the room and responding with care."),
    ("Ownership", "Acting like it's yours — because it is."),
    ("Elevation", "Raising the bar, never settling."),
]


SYSTEM_PREAMBLE = """You are the operational intelligence for The Uncommon Pursuit, \
the operating philosophy for luxury property management.

Your job is to produce recommendations that are specific, conviction-driven, and \
grounded in the canon. Avoid corporate filler — no "consider", no "evaluate", no \
"explore opportunities". State the move, name the standard it serves, and give a \
concrete next action the owner can take today.

Every recommendation must:
- Lead with the most relevant of the Seven Standards for this task.
- Frame the objective in terms of The Uncommon Pursuit's mission, not generic \
project management.
- Stay in the canon's voice: direct, warm, exacting.
- End with a single next action that is specific enough to execute today — not \
"schedule a meeting", but "draft the resident-facing note and send it to Alex \
for review by Friday at 5pm".

You MUST return a single JSON object and nothing else — no prose before or after, \
no markdown fences. The object must have exactly these keys:
  - "standard":               the single Standard that anchors this recommendation
  - "objective":               one sentence, mission-aligned
  - "first_principles_plan":   a short plan (3-5 sentences) derived from canon, \
not templates
  - "viable_options":          a JSON array of 2-3 strings, each one a distinct \
option with its trade-off
  - "next_action":             a single concrete action the owner can execute today
"""


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


def build_recommendation_system_prompt(context_chunks: Sequence[dict]) -> str:
    """Return the full system prompt for a recommendation call.

    ``context_chunks`` is the same list the mock provider already receives —
    the result of the embedding similarity search in services.retrieve_search.
    """
    sections = [
        SYSTEM_PREAMBLE,
        _format_seven_standards(),
        _format_retrieved_chunks(context_chunks),
    ]
    return "\n\n---\n\n".join(sections)


def build_recommendation_user_message(
    *,
    task_title: str,
    task_description: str,
    task_status: str,
    task_priority: str,
    owner_name: str,
    assigner_name: str,
    due_at_iso: str | None,
    objective_seed: str,
    standard_seed: str,
) -> str:
    """Return the user message body describing the task in question."""
    due_line = due_at_iso if due_at_iso else "not set"
    return (
        f"Task: {task_title}\n"
        f"Status: {task_status} | Priority: {task_priority}\n"
        f"Owner: {owner_name} | Assigned by: {assigner_name}\n"
        f"Due: {due_line}\n"
        f"\n"
        f"Current objective (may be refined): {objective_seed}\n"
        f"Current standard hint (may be refined): {standard_seed}\n"
        f"\n"
        f"Description and recent updates:\n{task_description}\n"
        f"\n"
        f"Produce the JSON recommendation now."
    )
