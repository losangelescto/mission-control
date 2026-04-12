from datetime import datetime, timezone

from app.mailbox.connector import MailboxConnector
from app.mailbox.types import MailboxMessageDTO

DEFAULT_FOLDER = "Inbox"


def default_fixture_messages(mailbox_owner: str, folder_name: str) -> list[MailboxMessageDTO]:
    t0 = datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 1, 11, 9, 30, 0, tzinfo=timezone.utc)
    return [
        MailboxMessageDTO(
            external_message_id="fixture-msg-alpha",
            external_thread_id="fixture-thread-1",
            mailbox_owner=mailbox_owner,
            folder_name=folder_name,
            sender="alice@example.com",
            recipients_json=[mailbox_owner],
            subject="Fixture: first message",
            body_text="Hello from fixture thread 1.",
            received_at=t0,
        ),
        MailboxMessageDTO(
            external_message_id="fixture-msg-beta",
            external_thread_id="fixture-thread-1",
            mailbox_owner=mailbox_owner,
            folder_name=folder_name,
            sender=mailbox_owner,
            recipients_json=["alice@example.com"],
            subject="Re: Fixture: first message",
            body_text="Reply in same thread.",
            received_at=t1,
        ),
        MailboxMessageDTO(
            external_message_id="fixture-msg-gamma",
            external_thread_id="fixture-thread-2",
            mailbox_owner=mailbox_owner,
            folder_name=folder_name,
            sender="ops@example.com",
            recipients_json=[mailbox_owner],
            subject="Fixture: other thread",
            body_text="Different conversation.",
            received_at=t1,
        ),
    ]


class FixtureMailboxConnector:
    """Deterministic in-memory connector for tests and local POC (no credentials)."""

    def __init__(self, messages: list[MailboxMessageDTO] | None = None) -> None:
        self._override: list[MailboxMessageDTO] | None = messages

    def fetch_messages(
        self,
        *,
        mailbox_owner: str,
        folder_name: str | None = None,
    ) -> list[MailboxMessageDTO]:
        resolved_folder = folder_name or DEFAULT_FOLDER
        if self._override is not None:
            return [
                MailboxMessageDTO(
                    external_message_id=m.external_message_id,
                    external_thread_id=m.external_thread_id,
                    mailbox_owner=mailbox_owner,
                    folder_name=resolved_folder,
                    sender=m.sender,
                    recipients_json=list(m.recipients_json),
                    subject=m.subject,
                    body_text=m.body_text,
                    received_at=m.received_at,
                )
                for m in self._override
            ]
        return default_fixture_messages(mailbox_owner, resolved_folder)
