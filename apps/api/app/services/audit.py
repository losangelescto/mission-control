"""Audit-trail logging.

Two ways to record an event:

- ``log_event(db, ...)`` — synchronous insert into the active session;
  flushes but does not commit. Cheap (low single-digit ms) and atomic
  with the surrounding transaction. Preferred for inline use inside an
  existing service operation that's already going to commit.

- ``schedule_event(background_tasks, ...)`` — fire-and-forget BG task
  that opens its own session, inserts, and commits. Use when there is
  no existing transaction or when the caller must return *before* the
  audit row is written (e.g. background pipelines).

The on-disk row matches the spec:

- ``entity_type`` (free-form string)
- ``entity_id``   (string — we accept ints and stringify them)
- ``action``      (canonical action verb)
- ``actor``       (user identifier or ``"system"`` for pipeline events)
- ``changes``     (JSON: ``{"field": {"old": ..., "new": ...}}``)
- ``metadata``    (JSON: free-form, e.g. ``{"recommendation_type": ...}``)

We never log full document content — only entity references and field
diffs, per the privacy constraint.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app import db as db_module
from app.models import AuditEvent

logger = logging.getLogger(__name__)

SYSTEM_ACTOR = "system"


def log_event(
    db: Session,
    *,
    entity_type: str,
    entity_id: int | str,
    action: str,
    actor: str = SYSTEM_ACTOR,
    changes: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent | None:
    """Insert an audit row in the active session. Returns the row.

    Wrapped in a SAVEPOINT so that an audit failure (missing table in a
    test fixture, JSON serialisation error, etc.) does not poison the
    surrounding transaction. We log and return ``None`` instead.
    """
    try:
        with db.begin_nested():
            event = AuditEvent(
                entity_type=entity_type,
                entity_id=str(entity_id),
                event_type=action,  # back-compat for legacy callers
                payload_json=changes or {},
                action=action,
                actor=actor or SYSTEM_ACTOR,
                changes=changes,
                event_metadata=metadata,
            )
            db.add(event)
            db.flush()
            return event
    except Exception:
        logger.exception(
            "audit log failed (sync)",
            extra={
                "context": {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "action": action,
                }
            },
        )
        return None


def schedule_event(
    background_tasks,
    *,
    entity_type: str,
    entity_id: int | str,
    action: str,
    actor: str = SYSTEM_ACTOR,
    changes: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Schedule a fire-and-forget BG insert.

    The BG task opens a fresh session via ``app.db.SessionLocal`` (so
    tests that monkeypatch ``SessionLocal`` get the test DB).
    """
    background_tasks.add_task(
        _persist_async,
        entity_type,
        str(entity_id),
        action,
        actor or SYSTEM_ACTOR,
        changes,
        metadata,
    )


def _persist_async(
    entity_type: str,
    entity_id: str,
    action: str,
    actor: str,
    changes: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
) -> None:
    db = db_module.SessionLocal()
    try:
        event = AuditEvent(
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=action,
            payload_json=changes or {},
            action=action,
            actor=actor,
            changes=changes,
            event_metadata=metadata,
        )
        db.add(event)
        db.commit()
    except Exception:
        logger.exception(
            "audit log failed (async)",
            extra={
                "context": {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "action": action,
                }
            },
        )
        db.rollback()
    finally:
        db.close()


def diff_fields(before: dict[str, Any], after: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    """Build a ``{field: {old, new}}`` map limited to the named fields.

    Skips fields where the value did not change. Used to keep audit
    payloads small and non-sensitive.
    """
    out: dict[str, Any] = {}
    for field in fields:
        old = before.get(field)
        new = after.get(field)
        if old != new:
            out[field] = {"old": old, "new": new}
    return out


__all__ = ["log_event", "schedule_event", "diff_fields", "SYSTEM_ACTOR"]
