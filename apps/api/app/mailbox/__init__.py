"""Mailbox connector layer (Phase 1: fixtures + Graph stub, no live mail)."""

from app.mailbox.fixture_connector import FixtureMailboxConnector
from app.mailbox.graph_stub import GraphMailboxConnectorStub

__all__ = [
    "FixtureMailboxConnector",
    "GraphMailboxConnectorStub",
]
