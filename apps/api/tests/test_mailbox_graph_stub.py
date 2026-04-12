import pytest

from app.config import Settings
from app.mailbox.graph_stub import (
    GraphMailboxConnectorStub,
    GraphMailboxNotConfiguredError,
    graph_mail_configured,
)


def test_graph_mail_not_configured_without_env() -> None:
    s = Settings(
        microsoft_graph_tenant_id=None,
        microsoft_graph_client_id=None,
        microsoft_graph_client_secret=None,
    )
    assert graph_mail_configured(s) is False
    stub = GraphMailboxConnectorStub(s)
    assert stub.is_enabled() is False
    with pytest.raises(GraphMailboxNotConfiguredError):
        stub.fetch_messages(mailbox_owner="u@example.com")


def test_graph_stub_disabled_when_use_graph_mailbox_false() -> None:
    s = Settings(
        microsoft_graph_tenant_id="tenant",
        microsoft_graph_client_id="client",
        microsoft_graph_client_secret="secret",
        use_graph_mailbox=False,
    )
    stub = GraphMailboxConnectorStub(s)
    assert stub.is_enabled() is False
    with pytest.raises(GraphMailboxNotConfiguredError):
        stub.fetch_messages(mailbox_owner="u@example.com")


def test_graph_stub_returns_message_when_configured() -> None:
    s = Settings(
        microsoft_graph_tenant_id="tenant",
        microsoft_graph_client_id="client",
        microsoft_graph_client_secret="secret",
        use_graph_mailbox=True,
    )
    assert graph_mail_configured(s) is True
    stub = GraphMailboxConnectorStub(s)
    msgs = stub.fetch_messages(mailbox_owner="u@example.com", folder_name=None)
    assert len(msgs) == 1
    assert msgs[0].external_message_id == "graph-stub-msg-1"
