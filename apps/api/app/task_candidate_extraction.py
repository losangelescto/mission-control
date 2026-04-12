import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol


@dataclass
class CandidateDraft:
    title: str
    description: str
    inferred_owner_name: str | None
    inferred_due_at: datetime | None
    fallback_due_at: datetime
    confidence: float
    urgency_hints: list[str] = field(default_factory=list)
    blocker_hints: list[str] = field(default_factory=list)
    recurrence_hints: list[str] = field(default_factory=list)
    completion_hints: list[str] = field(default_factory=list)
    delegation_hints: list[str] = field(default_factory=list)
    extraction_kind: str | None = None  # e.g. action_item, decision, blocker, follow_up (call artifacts)


def candidate_draft_hints_json(draft: CandidateDraft) -> dict:
    out = {
        "urgency": list(draft.urgency_hints),
        "blocker": list(draft.blocker_hints),
        "recurrence": list(draft.recurrence_hints),
        "completion": list(draft.completion_hints),
        "delegation": list(draft.delegation_hints),
    }
    if draft.extraction_kind:
        out["extraction_kind"] = draft.extraction_kind
    return out


class AIExtractionInterface(Protocol):
    def extract_candidates(self, source_text: str) -> list[CandidateDraft]:
        ...


class NullAIExtractor:
    def extract_candidates(self, source_text: str) -> list[CandidateDraft]:
        return []


_DATE_PATTERN = re.compile(r"(20\d{2}-\d{2}-\d{2})")
_OWNER_PATTERN = re.compile(r"owner:\s*([A-Za-z][A-Za-z .'-]+)", re.IGNORECASE)


def _parse_due_date(text: str) -> datetime | None:
    match = _DATE_PATTERN.search(text)
    if not match:
        return None
    return datetime.fromisoformat(match.group(1)).replace(tzinfo=UTC)


def _parse_owner(text: str) -> str | None:
    match = _OWNER_PATTERN.search(text)
    if match:
        raw = match.group(1).strip()
        stop_words = {"follow", "with", "by", "due", "task", "todo", "action"}
        tokens = [token for token in raw.split() if token]
        owner_tokens: list[str] = []
        for token in tokens:
            if token.lower() in stop_words:
                break
            owner_tokens.append(token)
            if len(owner_tokens) == 2:
                break
        if owner_tokens:
            return " ".join(owner_tokens)
    return None


def _collect_hints(text: str) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    lowered = text.lower()
    urgency = [word for word in ["urgent", "asap", "today", "eod"] if word in lowered]
    blockers = [word for word in ["blocked", "waiting on", "dependency"] if word in lowered]
    recurrence = [word for word in ["daily", "weekly", "monthly", "every"] if word in lowered]
    completion = [word for word in ["done", "completed", "resolved", "shipped", "closed"] if word in lowered]
    delegation = [word for word in ["delegate", "reassign", "loop in", "cc:", "forward to"] if word in lowered]
    return urgency, blockers, recurrence, completion, delegation


def extract_task_candidates_with_heuristics(
    *,
    source_text: str,
    source_date: datetime,
) -> list[CandidateDraft]:
    drafts: list[CandidateDraft] = []
    lines = [line.strip() for line in source_text.splitlines() if line.strip()]
    for line in lines:
        lowered = line.lower()
        if not any(token in lowered for token in ["todo", "task", "follow up", "need to", "action"]):
            continue

        inferred_due = _parse_due_date(line)
        fallback_due = (source_date + timedelta(days=7)).replace(tzinfo=UTC)
        owner = _parse_owner(line)
        urgency_hints, blocker_hints, recurrence_hints, completion_hints, delegation_hints = _collect_hints(
            line
        )

        description = "\n".join(
            [
                line,
                f"urgency_hints: {', '.join(urgency_hints) if urgency_hints else 'none'}",
                f"blocker_hints: {', '.join(blocker_hints) if blocker_hints else 'none'}",
                f"recurrence_hints: {', '.join(recurrence_hints) if recurrence_hints else 'none'}",
                f"completion_hints: {', '.join(completion_hints) if completion_hints else 'none'}",
                f"delegation_hints: {', '.join(delegation_hints) if delegation_hints else 'none'}",
            ]
        )

        drafts.append(
            CandidateDraft(
                title=line[:255],
                description=description,
                inferred_owner_name=owner,
                inferred_due_at=inferred_due,
                fallback_due_at=fallback_due,
                confidence=0.55,
                urgency_hints=urgency_hints,
                blocker_hints=blocker_hints,
                recurrence_hints=recurrence_hints,
                completion_hints=completion_hints,
                delegation_hints=delegation_hints,
            )
        )

    return drafts
