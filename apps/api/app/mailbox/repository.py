from datetime import datetime, timezone


def _as_utc_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MailboxMessage, MailboxSource, MailboxSyncState, MailboxThread


def get_mailbox_source(
    db: Session,
    *,
    provider: str,
    mailbox_owner: str,
    folder_name: str,
) -> MailboxSource | None:
    stmt = select(MailboxSource).where(
        MailboxSource.provider == provider,
        MailboxSource.mailbox_owner == mailbox_owner,
        MailboxSource.folder_name == folder_name,
    )
    return db.scalar(stmt)


def get_or_create_mailbox_source(
    db: Session,
    *,
    provider: str,
    mailbox_owner: str,
    folder_name: str,
) -> MailboxSource:
    stmt = select(MailboxSource).where(
        MailboxSource.provider == provider,
        MailboxSource.mailbox_owner == mailbox_owner,
        MailboxSource.folder_name == folder_name,
    )
    existing = db.scalar(stmt)
    if existing:
        return existing
    row = MailboxSource(
        provider=provider,
        mailbox_owner=mailbox_owner,
        folder_name=folder_name,
    )
    db.add(row)
    db.flush()
    return row


def upsert_thread(
    db: Session,
    *,
    mailbox_source_id: int,
    external_thread_id: str,
    subject: str | None,
    message_received_at: datetime,
) -> MailboxThread:
    incoming = _as_utc_aware(message_received_at)
    stmt = select(MailboxThread).where(
        MailboxThread.mailbox_source_id == mailbox_source_id,
        MailboxThread.external_thread_id == external_thread_id,
    )
    thread = db.scalar(stmt)
    if thread is None:
        thread = MailboxThread(
            mailbox_source_id=mailbox_source_id,
            external_thread_id=external_thread_id,
            subject=subject,
            last_message_at=incoming,
        )
        db.add(thread)
        db.flush()
        return thread
    if subject:
        thread.subject = subject
    existing_last = _as_utc_aware(thread.last_message_at)
    if incoming > existing_last:
        thread.last_message_at = incoming
    db.add(thread)
    db.flush()
    return thread


def insert_message_if_new(
    db: Session,
    *,
    mailbox_source_id: int,
    mailbox_thread_id: int,
    external_message_id: str,
    external_thread_id: str,
    mailbox_owner: str,
    folder_name: str,
    sender: str,
    recipients_json: list,
    subject: str,
    body_text: str,
    received_at: datetime,
    source_document_id: int | None,
) -> MailboxMessage | None:
    """Insert message; return None if duplicate external_message_id for this source."""
    dup = db.scalar(
        select(MailboxMessage.id).where(
            MailboxMessage.mailbox_source_id == mailbox_source_id,
            MailboxMessage.external_message_id == external_message_id,
        )
    )
    if dup is not None:
        return None
    row = MailboxMessage(
        mailbox_source_id=mailbox_source_id,
        mailbox_thread_id=mailbox_thread_id,
        external_message_id=external_message_id,
        external_thread_id=external_thread_id,
        mailbox_owner=mailbox_owner,
        folder_name=folder_name,
        sender=sender,
        recipients_json=recipients_json,
        subject=subject,
        body_text=body_text,
        received_at=received_at,
        source_document_id=source_document_id,
    )
    db.add(row)
    db.flush()
    return row


def get_sync_state(db: Session, mailbox_source_id: int) -> MailboxSyncState | None:
    return db.scalar(select(MailboxSyncState).where(MailboxSyncState.mailbox_source_id == mailbox_source_id))


def upsert_sync_state(
    db: Session,
    *,
    mailbox_source_id: int,
    status: str,
    cursor_json: dict,
) -> MailboxSyncState:
    row = get_sync_state(db, mailbox_source_id)
    now = datetime.now(timezone.utc)
    if row is None:
        row = MailboxSyncState(
            mailbox_source_id=mailbox_source_id,
            last_synced_at=now,
            cursor_json=cursor_json,
            status=status,
        )
        db.add(row)
    else:
        row.last_synced_at = now
        row.cursor_json = cursor_json
        row.status = status
        db.add(row)
    db.flush()
    return row


def list_messages(
    db: Session,
    *,
    mailbox_owner: str | None,
    mailbox_source_id: int | None,
    thread_external_id: str | None,
) -> list[MailboxMessage]:
    stmt = select(MailboxMessage).order_by(MailboxMessage.received_at.desc())
    if mailbox_owner:
        stmt = stmt.where(MailboxMessage.mailbox_owner == mailbox_owner)
    if mailbox_source_id is not None:
        stmt = stmt.where(MailboxMessage.mailbox_source_id == mailbox_source_id)
    if thread_external_id:
        stmt = stmt.where(MailboxMessage.external_thread_id == thread_external_id)
    return list(db.scalars(stmt).all())


def get_message_by_id(db: Session, message_id: int) -> MailboxMessage | None:
    return db.get(MailboxMessage, message_id)


def get_thread_by_external_id(
    db: Session,
    *,
    mailbox_source_id: int,
    external_thread_id: str,
) -> MailboxThread | None:
    stmt = select(MailboxThread).where(
        MailboxThread.mailbox_source_id == mailbox_source_id,
        MailboxThread.external_thread_id == external_thread_id,
    )
    return db.scalar(stmt)


def list_messages_for_thread(
    db: Session,
    *,
    mailbox_thread_id: int,
) -> list[MailboxMessage]:
    stmt = (
        select(MailboxMessage)
        .where(MailboxMessage.mailbox_thread_id == mailbox_thread_id)
        .order_by(MailboxMessage.received_at.asc())
    )
    return list(db.scalars(stmt).all())
