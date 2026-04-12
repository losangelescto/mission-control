from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MailboxMessageDTO:
    """Normalized message shape for connector implementations (before persistence)."""

    external_message_id: str
    external_thread_id: str
    mailbox_owner: str
    folder_name: str
    sender: str
    recipients_json: list[str]
    subject: str
    body_text: str
    received_at: datetime
