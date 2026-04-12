from datetime import datetime, timezone

from app.config import Settings, get_settings
from app.mailbox.types import MailboxMessageDTO

DEFAULT_FOLDER = "Inbox"


def graph_mail_configured(settings: Settings) -> bool:
    """Graph stub is only considered enabled when all three credential placeholders are set."""
    return bool(
        settings.microsoft_graph_tenant_id
        and settings.microsoft_graph_client_id
        and settings.microsoft_graph_client_secret
    )


class GraphMailboxNotConfiguredError(RuntimeError):
    pass


class GraphMailboxConnectorStub:
    """
    Isolated Microsoft Graph-shaped stub (no HTTP, no send-mail).
    Disabled unless tenant/client id/secret env vars are present.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "GraphMailboxConnectorStub":
        return cls(settings or get_settings())

    def is_enabled(self) -> bool:
        return bool(
            self._settings.use_graph_mailbox and graph_mail_configured(self._settings)
        )

    def fetch_messages(
        self,
        *,
        mailbox_owner: str,
        folder_name: str | None = None,
    ) -> list[MailboxMessageDTO]:
        if not self.is_enabled():
            raise GraphMailboxNotConfiguredError(
                "Graph mailbox stub is disabled; set USE_GRAPH_MAILBOX=true and "
                "MICROSOFT_GRAPH_TENANT_ID, MICROSOFT_GRAPH_CLIENT_ID, and MICROSOFT_GRAPH_CLIENT_SECRET"
            )
        resolved_folder = folder_name or DEFAULT_FOLDER
        now = datetime.now(timezone.utc)
        return [
            MailboxMessageDTO(
                external_message_id="graph-stub-msg-1",
                external_thread_id="graph-stub-thread-1",
                mailbox_owner=mailbox_owner,
                folder_name=resolved_folder,
                sender="graph.stub@example.com",
                recipients_json=[mailbox_owner],
                subject="Graph stub message",
                body_text="Stub body (no network).",
                received_at=now,
            )
        ]
