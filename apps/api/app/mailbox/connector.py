from typing import Protocol

from app.mailbox.types import MailboxMessageDTO


class MailboxConnector(Protocol):
    """Phase 1 mailbox ingest connector (Exchange / Microsoft Graph architecture hook)."""

    def fetch_messages(
        self,
        *,
        mailbox_owner: str,
        folder_name: str | None = None,
    ) -> list[MailboxMessageDTO]:
        """Return messages for the mailbox. Folder defaults to Inbox when unspecified."""
        ...
