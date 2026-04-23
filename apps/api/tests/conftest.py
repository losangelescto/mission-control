"""Shared pytest fixtures.

Tests share a single FastAPI app instance (and therefore a single slowapi
limiter with in-memory counters). Without this autouse reset, the order in
which tests run can cause later tests to hit 429s on endpoints that are
rate-limited per IP — e.g. /tasks/{id}/recommendation at 10/minute.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def reset_rate_limiter() -> None:
    from app.security import limiter

    limiter.reset()
