import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.mailbox.fixture_connector import FixtureMailboxConnector
from app.mailbox.repository import (
    get_mailbox_source,
    get_or_create_mailbox_source,
    get_thread_by_external_id,
    insert_message_if_new,
    list_messages_for_thread,
    upsert_sync_state,
    upsert_thread,
)
from app.mailbox.types import MailboxMessageDTO
from app.models import MailboxMessage, MailboxSource, MailboxThread

FIXTURE_PROVIDER = "fixture"
logger = logging.getLogger(__name__)


def sync_fixture_mail(
    db: Session,
    *,
    mailbox_owner: str,
    folder_name: str | None,
    connector: FixtureMailboxConnector | None = None,
) -> tuple[MailboxSource, int, int]:
    """
    Pull messages from FixtureMailboxConnector and persist with dedupe + thread grouping.
    Returns (source, inserted_count, skipped_duplicate_count).
    """
    resolved_folder = folder_name or "Inbox"
    conn = connector or FixtureMailboxConnector()
    logger.info(
        "mailbox fixture sync started",
        extra={
            "event": "mailbox_sync_started",
            "context": {
                "provider": FIXTURE_PROVIDER,
                "mailbox_owner": mailbox_owner,
                "folder_name": resolved_folder,
            },
        },
    )
    dtos = conn.fetch_messages(mailbox_owner=mailbox_owner, folder_name=resolved_folder)
    source = get_or_create_mailbox_source(
        db,
        provider=FIXTURE_PROVIDER,
        mailbox_owner=mailbox_owner,
        folder_name=resolved_folder,
    )
    inserted = 0
    skipped = 0
    for dto in dtos:
        thread = upsert_thread(
            db,
            mailbox_source_id=source.id,
            external_thread_id=dto.external_thread_id,
            subject=dto.subject,
            message_received_at=dto.received_at,
        )
        msg = insert_message_if_new(
            db,
            mailbox_source_id=source.id,
            mailbox_thread_id=thread.id,
            external_message_id=dto.external_message_id,
            external_thread_id=dto.external_thread_id,
            mailbox_owner=dto.mailbox_owner,
            folder_name=dto.folder_name,
            sender=dto.sender,
            recipients_json=list(dto.recipients_json),
            subject=dto.subject,
            body_text=dto.body_text,
            received_at=dto.received_at,
            source_document_id=None,
        )
        if msg is None:
            skipped += 1
        else:
            inserted += 1
    upsert_sync_state(
        db,
        mailbox_source_id=source.id,
        status="ok",
        cursor_json={"fixture": True, "synced_at": datetime.now(timezone.utc).isoformat()},
    )
    db.commit()
    db.refresh(source)
    logger.info(
        "mailbox fixture sync completed",
        extra={
            "event": "mailbox_sync_completed",
            "context": {
                "provider": FIXTURE_PROVIDER,
                "mailbox_owner": mailbox_owner,
                "mailbox_source_id": source.id,
                "inserted": inserted,
                "skipped_duplicates": skipped,
            },
        },
    )
    return source, inserted, skipped


def sync_fixture_mail_from_dtos(
    db: Session,
    *,
    mailbox_owner: str,
    folder_name: str | None,
    dtos: list[MailboxMessageDTO],
) -> tuple[MailboxSource, int, int]:
    """
    Persist pre-built DTOs (e.g. from request body) using fixture provider source.
    """
    resolved_folder = folder_name or "Inbox"
    logger.info(
        "mailbox fixture sync started (from DTOs)",
        extra={
            "event": "mailbox_sync_started",
            "context": {
                "provider": FIXTURE_PROVIDER,
                "mailbox_owner": mailbox_owner,
                "folder_name": resolved_folder,
                "dto_count": len(dtos),
            },
        },
    )
    source = get_or_create_mailbox_source(
        db,
        provider=FIXTURE_PROVIDER,
        mailbox_owner=mailbox_owner,
        folder_name=resolved_folder,
    )
    inserted = 0
    skipped = 0
    for dto in dtos:
        thread = upsert_thread(
            db,
            mailbox_source_id=source.id,
            external_thread_id=dto.external_thread_id,
            subject=dto.subject,
            message_received_at=dto.received_at,
        )
        msg = insert_message_if_new(
            db,
            mailbox_source_id=source.id,
            mailbox_thread_id=thread.id,
            external_message_id=dto.external_message_id,
            external_thread_id=dto.external_thread_id,
            mailbox_owner=dto.mailbox_owner,
            folder_name=dto.folder_name,
            sender=dto.sender,
            recipients_json=list(dto.recipients_json),
            subject=dto.subject,
            body_text=dto.body_text,
            received_at=dto.received_at,
            source_document_id=None,
        )
        if msg is None:
            skipped += 1
        else:
            inserted += 1
    upsert_sync_state(
        db,
        mailbox_source_id=source.id,
        status="ok",
        cursor_json={"fixture": True, "synced_at": datetime.now(timezone.utc).isoformat()},
    )
    db.commit()
    db.refresh(source)
    logger.info(
        "mailbox fixture sync completed (from DTOs)",
        extra={
            "event": "mailbox_sync_completed",
            "context": {
                "provider": FIXTURE_PROVIDER,
                "mailbox_owner": mailbox_owner,
                "mailbox_source_id": source.id,
                "inserted": inserted,
                "skipped_duplicates": skipped,
            },
        },
    )
    return source, inserted, skipped


def get_mailbox_message(db: Session, message_id: int) -> MailboxMessage | None:
    from app.mailbox.repository import get_message_by_id

    return get_message_by_id(db, message_id)


def get_thread_by_external(
    db: Session,
    *,
    mailbox_owner: str,
    folder_name: str | None,
    external_thread_id: str,
) -> tuple[MailboxThread, list[MailboxMessage]] | None:
    resolved_folder = folder_name or "Inbox"
    source = get_mailbox_source(
        db,
        provider=FIXTURE_PROVIDER,
        mailbox_owner=mailbox_owner,
        folder_name=resolved_folder,
    )
    if source is None:
        return None
    thread = get_thread_by_external_id(
        db,
        mailbox_source_id=source.id,
        external_thread_id=external_thread_id,
    )
    if thread is None:
        return None
    messages = list_messages_for_thread(db, mailbox_thread_id=thread.id)
    return thread, messages
