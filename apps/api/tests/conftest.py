"""Shared pytest fixtures.

Tests share a single FastAPI app instance (and therefore a single slowapi
limiter with in-memory counters). Without this autouse reset, the order in
which tests run can cause later tests to hit 429s on endpoints that are
rate-limited per IP — e.g. /tasks/{id}/recommendation at 10/minute.

The ``disable_auto_extract`` fixture defaults source ingestion to
non-extracting so tests that only build the SourceDocument/SourceChunk
tables don't trip over a missing task_candidates table. Tests that need
auto-extraction explicitly flip the flag back on.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def reset_rate_limiter() -> None:
    from app.security import limiter

    limiter.reset()


@pytest.fixture(autouse=True)
def disable_auto_extract() -> None:
    from app.config import get_settings

    settings = get_settings()
    original = settings.auto_extract_tasks
    settings.auto_extract_tasks = False
    yield
    settings.auto_extract_tasks = original
