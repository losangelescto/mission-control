"""
Email / thread extraction on top of shared heuristics + AI extraction interface.
"""

from datetime import UTC, datetime, timedelta

from app.task_candidate_extraction import (
    AIExtractionInterface,
    CandidateDraft,
    NullAIExtractor,
    _collect_hints,
    _parse_due_date,
    _parse_owner,
    extract_task_candidates_with_heuristics,
)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def extract_task_candidates_from_email_text(
    *,
    subject: str,
    body: str,
    received_at: datetime,
    ai_extractor: AIExtractionInterface | None = None,
) -> list[CandidateDraft]:
    """
    Build task candidates from a single message (subject + body).
    explicit_due_at from body; fallback_due_at = received_at + 7 days (standard).
    """
    extractor = ai_extractor or NullAIExtractor()
    received = _as_utc(received_at)
    full_text = f"Subject: {subject}\n\n{body}"
    heuristic = extract_task_candidates_with_heuristics(source_text=full_text, source_date=received)
    if not heuristic and any(
        token in full_text.lower()
        for token in ["todo", "task", "follow up", "need to", "action", "owner:"]
    ):
        inferred_due = _parse_due_date(full_text)
        fallback_due = (received + timedelta(days=7)).replace(tzinfo=UTC)
        owner = _parse_owner(full_text)
        u, b, r, c, d = _collect_hints(full_text)
        heuristic = [
            CandidateDraft(
                title=(subject or "Email task")[:255],
                description="\n".join(
                    [
                        full_text[:8000],
                        f"urgency_hints: {', '.join(u) if u else 'none'}",
                        f"blocker_hints: {', '.join(b) if b else 'none'}",
                        f"recurrence_hints: {', '.join(r) if r else 'none'}",
                        f"completion_hints: {', '.join(c) if c else 'none'}",
                        f"delegation_hints: {', '.join(d) if d else 'none'}",
                    ]
                ),
                inferred_owner_name=owner,
                inferred_due_at=inferred_due,
                fallback_due_at=fallback_due,
                confidence=0.5,
                urgency_hints=u,
                blocker_hints=b,
                recurrence_hints=r,
                completion_hints=c,
                delegation_hints=d,
            )
        ]
    ai_extra = extractor.extract_candidates(full_text)
    return [*heuristic, *ai_extra]


def extract_thread_refresh_suggestions(
    *,
    thread_subject: str,
    new_message_bodies: list[str],
    source_date: datetime,
    ai_extractor: AIExtractionInterface | None = None,
) -> list[CandidateDraft]:
    """
    Inspect new thread messages for completion / blocker / follow-up signals.
    Returns review-only CandidateDraft rows (caller sets candidate_kind=thread_state_suggestion).
    """
    extractor = ai_extractor or NullAIExtractor()
    if not new_message_bodies:
        return []
    combined = "\n---\n".join(new_message_bodies)
    text = f"Thread: {thread_subject}\n\n{combined}"
    source = _as_utc(source_date)
    drafts: list[CandidateDraft] = []

    u, b, r, c, d = _collect_hints(text)
    if c:
        drafts.append(
            CandidateDraft(
                title=f"Possible completion signal: {thread_subject[:120]}",
                description=(
                    "Review-only suggestion: text suggests work may be complete.\n\n"
                    f"Signals: {', '.join(c)}\n\nExcerpt:\n{combined[:4000]}"
                ),
                inferred_owner_name=None,
                inferred_due_at=None,
                fallback_due_at=(source + timedelta(days=7)).replace(tzinfo=UTC),
                confidence=0.45,
                urgency_hints=u,
                blocker_hints=b,
                recurrence_hints=r,
                completion_hints=c,
                delegation_hints=d,
            )
        )
    if b:
        drafts.append(
            CandidateDraft(
                title=f"Possible blocker / dependency: {thread_subject[:120]}",
                description=(
                    "Review-only suggestion: blocker-like language detected.\n\n"
                    f"Signals: {', '.join(b)}\n\nExcerpt:\n{combined[:4000]}"
                ),
                inferred_owner_name=None,
                inferred_due_at=None,
                fallback_due_at=(source + timedelta(days=7)).replace(tzinfo=UTC),
                confidence=0.45,
                urgency_hints=u,
                blocker_hints=b,
                recurrence_hints=r,
                completion_hints=c,
                delegation_hints=d,
            )
        )
    if any(k in text.lower() for k in ["follow up", "next step", "reminder", "ping"]):
        drafts.append(
            CandidateDraft(
                title=f"Follow-up / reminder signal: {thread_subject[:120]}",
                description=(
                    "Review-only suggestion: follow-up language detected.\n\n" f"Excerpt:\n{combined[:4000]}"
                ),
                inferred_owner_name=None,
                inferred_due_at=None,
                fallback_due_at=(source + timedelta(days=7)).replace(tzinfo=UTC),
                confidence=0.4,
                urgency_hints=u,
                blocker_hints=b,
                recurrence_hints=r,
                completion_hints=c,
                delegation_hints=d,
            )
        )
    if d:
        drafts.append(
            CandidateDraft(
                title=f"Delegation / handoff signal: {thread_subject[:120]}",
                description=(
                    "Review-only suggestion: delegation-like language detected.\n\n"
                    f"Signals: {', '.join(d)}\n\nExcerpt:\n{combined[:4000]}"
                ),
                inferred_owner_name=None,
                inferred_due_at=None,
                fallback_due_at=(source + timedelta(days=7)).replace(tzinfo=UTC),
                confidence=0.4,
                urgency_hints=u,
                blocker_hints=b,
                recurrence_hints=r,
                completion_hints=c,
                delegation_hints=d,
            )
        )

    drafts.extend(extractor.extract_candidates(text))
    return drafts
