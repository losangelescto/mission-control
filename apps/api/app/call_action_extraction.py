"""
Heuristics for extracting actionable items from call transcripts, summaries, and notes.
Outputs shared CandidateDraft rows (merged into task_candidates).
"""

import re
from datetime import UTC, datetime, timedelta

from app.task_candidate_extraction import CandidateDraft, _parse_due_date, _parse_owner


_ACTION_LINE = re.compile(
    r"^\s*(?:[-*•]|\d+[.)]|\[[ x]\])\s*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)
_ACTION_PREFIX = re.compile(
    r"^\s*(?:action(?:\s*item)?|todo|follow[- ]?up|next step)\s*[:.-]\s*(.+)$",
    re.IGNORECASE,
)
_DECISION_PREFIX = re.compile(
    r"^\s*(?:decision|agreed|resolved|conclusion)\s*[:.-]\s*(.+)$",
    re.IGNORECASE,
)
_BLOCKER_PREFIX = re.compile(
    r"^\s*(?:blocker|blocked|risk|dependency|waiting on)\s*[:.-]\s*(.+)$",
    re.IGNORECASE,
)


def _fallback_due(source_date: datetime) -> datetime:
    return (source_date + timedelta(days=7)).replace(tzinfo=UTC)


def _hint_lists_for_line(line: str) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    """Reuse urgency/blocker/completion/delegation style hints for call lines."""
    lowered = line.lower()
    urgency = [w for w in ["urgent", "asap", "today", "eod"] if w in lowered]
    blocker = [w for w in ["blocked", "waiting", "dependency", "risk"] if w in lowered]
    completion = [w for w in ["done", "decided", "agreed"] if w in lowered]
    delegation = [w for w in ["delegate", "owner", "assign"] if w in lowered]
    recurrence: list[str] = []
    return urgency, blocker, recurrence, completion, delegation


def extract_call_actions_heuristics(
    *,
    source_text: str,
    source_date: datetime,
) -> list[CandidateDraft]:
    """Identify action items, decisions, blockers, follow-ups; owners and due dates when present."""
    drafts: list[CandidateDraft] = []
    seen: set[str] = set()
    source_utc = source_date if source_date.tzinfo else source_date.replace(tzinfo=UTC)

    lines = [ln.strip() for ln in source_text.splitlines() if ln.strip()]

    def add_draft(
        *,
        kind: str,
        title: str,
        body: str,
        line: str,
    ) -> None:
        key = f"{kind}:{title[:120]}"
        if key in seen:
            return
        seen.add(key)
        inferred_due = _parse_due_date(line) or _parse_due_date(body)
        fb = _fallback_due(source_utc)
        owner = _parse_owner(line) or _parse_owner(body)
        u, b, r, c, d = _hint_lists_for_line(line + " " + body)
        desc = "\n".join(
            [
                f"[{kind}] {body}",
                f"extraction_kind: {kind}",
                f"urgency_hints: {', '.join(u) if u else 'none'}",
                f"blocker_hints: {', '.join(b) if b else 'none'}",
                f"follow_up_signals: {', '.join(d) if d else 'none'}",
            ]
        )
        drafts.append(
            CandidateDraft(
                title=title[:255],
                description=desc,
                inferred_owner_name=owner,
                inferred_due_at=inferred_due,
                fallback_due_at=fb,
                confidence=0.52,
                urgency_hints=u,
                blocker_hints=b,
                recurrence_hints=r,
                completion_hints=c,
                delegation_hints=d,
                extraction_kind=kind,
            )
        )

    for line in lines:
        m = _DECISION_PREFIX.match(line)
        if m:
            add_draft(kind="decision", title=f"Decision: {m.group(1)[:200]}", body=m.group(1), line=line)
            continue
        m = _BLOCKER_PREFIX.match(line)
        if m:
            add_draft(kind="blocker", title=f"Blocker: {m.group(1)[:200]}", body=m.group(1), line=line)
            continue
        m = _ACTION_PREFIX.match(line)
        if m:
            add_draft(kind="action_item", title=m.group(1)[:255], body=m.group(1), line=line)
            continue
        m = _ACTION_LINE.match(line)
        if m and any(
            k in line.lower()
            for k in ["todo", "action", "follow", "owner", "due", "by ", "will ", "need"]
        ):
            add_draft(kind="action_item", title=m.group(1)[:255], body=m.group(1), line=line)

    # Follow-up commitments (paragraph-level, at most one aggregate)
    blob = "\n".join(lines)
    if re.search(r"follow[- ]?up|next step|commit to|will send|will schedule", blob, re.IGNORECASE):
        if "follow_up:once" not in seen:
            seen.add("follow_up:once")
            owner = _parse_owner(blob)
            inferred = _parse_due_date(blob)
            u, b, r, c, d = _hint_lists_for_line(blob)
            drafts.append(
                CandidateDraft(
                    title="Follow-up commitment (from call)",
                    description="\n".join(
                        [
                            blob[:6000],
                            "extraction_kind: follow_up",
                            f"urgency_hints: {', '.join(u) if u else 'none'}",
                        ]
                    ),
                    inferred_owner_name=owner,
                    inferred_due_at=inferred,
                    fallback_due_at=_fallback_due(source_utc),
                    confidence=0.48,
                    urgency_hints=u,
                    blocker_hints=b,
                    recurrence_hints=r,
                    completion_hints=c,
                    delegation_hints=d,
                    extraction_kind="follow_up",
                )
            )

    return drafts
