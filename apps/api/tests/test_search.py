"""Search service tests.

The Postgres FTS DDL (migration 0017) is exercised in real environments;
these unit tests cover the orchestration: type-filter routing, rank
ordering, pagination, and response envelope.
"""
from __future__ import annotations

from unittest.mock import patch

from app.services import search as search_module
from app.services.search import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    _runners_for_filter,
    _search_canon,
    _search_obstacles,
    _search_reviews,
    _search_source_chunks,
    _search_sources,
    _search_sub_tasks,
    _search_task_updates,
    _search_tasks,
    search,
)


def _stub_runner(rows: list[dict]):
    def _fn(db, q, limit):  # noqa: ARG001
        return rows
    return _fn


def test_runners_for_filter_all_includes_every_runner() -> None:
    runners = _runners_for_filter("all")
    assert _search_tasks in runners
    assert _search_task_updates in runners
    assert _search_sub_tasks in runners
    assert _search_obstacles in runners
    assert _search_sources in runners
    assert _search_source_chunks in runners
    assert _search_reviews in runners
    assert _search_canon in runners


def test_runners_for_filter_tasks_excludes_sources_and_canon() -> None:
    runners = _runners_for_filter("tasks")
    assert _search_sources not in runners
    assert _search_source_chunks not in runners
    assert _search_canon not in runners
    assert _search_reviews not in runners


def test_runners_for_filter_sources_excludes_canon() -> None:
    runners = _runners_for_filter("sources")
    assert _search_sources in runners
    assert _search_source_chunks in runners
    assert _search_canon not in runners


def test_runners_for_filter_canon_only_canon() -> None:
    assert _runners_for_filter("canon") == [_search_canon]


def test_runners_for_filter_unknown_returns_all() -> None:
    runners = _runners_for_filter("unknown")  # type: ignore[arg-type]
    assert len(runners) == 8


def test_search_returns_empty_for_blank_query() -> None:
    out = search(None, query="   ")  # db unused on early return
    assert out == {"results": [], "total": 0, "type_counts": {}, "mode": "keyword"}


def test_search_orders_by_relevance_and_paginates(monkeypatch) -> None:
    high = {"id": 1, "type": "task", "title": "high", "snippet": "", "relevance": 0.9, "url": "/", "metadata": {}}
    low = {"id": 2, "type": "task", "title": "low", "snippet": "", "relevance": 0.1, "url": "/", "metadata": {}}
    mid = {"id": 3, "type": "review", "title": "mid", "snippet": "", "relevance": 0.5, "url": "/", "metadata": {}}

    def fake_runners(_filter):
        return [_stub_runner([low]), _stub_runner([high, mid])]

    monkeypatch.setattr(search_module, "_runners_for_filter", fake_runners)
    monkeypatch.setattr(search_module, "_count_by_type", lambda *_a, **_k: {"tasks": 2, "reviews": 1})

    out = search(None, query="anything", type_filter="all", limit=2, offset=0)
    assert [r["title"] for r in out["results"]] == ["high", "mid"]
    assert out["total"] == 3

    out = search(None, query="anything", type_filter="all", limit=2, offset=2)
    assert [r["title"] for r in out["results"]] == ["low"]
    assert out["total"] == 3
    assert out["type_counts"] == {"tasks": 2, "reviews": 1}


def test_search_clamps_limit(monkeypatch) -> None:
    captured = {}

    def fake_runners(_filter):
        def _runner(_db, _q, limit):
            captured["limit"] = limit
            return []
        return [_runner]

    monkeypatch.setattr(search_module, "_runners_for_filter", fake_runners)
    monkeypatch.setattr(search_module, "_count_by_type", lambda *_a, **_k: {})

    search(None, query="x", limit=10_000)
    # runners are asked for limit+offset items so paging works post-merge.
    assert captured["limit"] == MAX_LIMIT


def test_search_swallows_runner_failure(monkeypatch) -> None:
    good_row = {
        "id": 1, "type": "task", "title": "ok", "snippet": "", "relevance": 0.5, "url": "/", "metadata": {}
    }

    def boom(_db, _q, _limit):
        raise RuntimeError("no table")

    def fake_runners(_filter):
        return [boom, _stub_runner([good_row])]

    monkeypatch.setattr(search_module, "_runners_for_filter", fake_runners)
    monkeypatch.setattr(search_module, "_count_by_type", lambda *_a, **_k: {})

    out = search(None, query="x")
    assert len(out["results"]) == 1
    assert out["results"][0]["title"] == "ok"


def test_semantic_mode_routes_to_semantic_search(monkeypatch) -> None:
    sentinel = [{"id": 9, "type": "source_chunk", "title": "doc", "snippet": "", "relevance": 0.95, "url": "/", "metadata": {}}]

    def fake_semantic(_db, *, query, limit, offset):  # noqa: ARG001
        return sentinel

    monkeypatch.setattr(search_module, "_semantic_search", fake_semantic)

    out = search(None, query="anything", mode="semantic")
    assert out["mode"] == "semantic"
    assert out["results"] == sentinel
    assert out["type_counts"] == {"source_chunk": 1}


def test_default_limit_is_in_range() -> None:
    assert 1 <= DEFAULT_LIMIT <= MAX_LIMIT


def test_sources_count_includes_chunks(monkeypatch) -> None:
    """When the only match for a query lives in a chunk, the facet count
    for ``sources`` must still reflect that hit. (Regression for the
    sidebar "Sources (0)" bug.)"""
    chunk_hit = {
        "id": 7,
        "type": "source_chunk",
        "title": "vendor.pdf",
        "snippet": "<mark>roof</mark> section needs attention",
        "relevance": 1.2,
        "url": "/sources?source_id=7",
        "metadata": {"source_type": "thread_export", "chunk_index": 0},
    }

    def fake_runners(_filter):
        return [_stub_runner([chunk_hit])]

    def fake_count_by_type(_db, _q):
        # Mirrors the new SQL contract: a chunk-only match increments
        # the per-document "sources" facet via the UNION fold.
        return {
            "tasks": 0, "task_updates": 0, "sub_tasks": 0, "obstacles": 0,
            "sources": 1, "reviews": 0, "canon": 0,
        }

    monkeypatch.setattr(search_module, "_runners_for_filter", fake_runners)
    monkeypatch.setattr(search_module, "_count_by_type", fake_count_by_type)

    out = search(None, query="roof", type_filter="all")
    assert out["type_counts"]["sources"] == 1
    assert any(r["type"] == "source_chunk" for r in out["results"])


def test_counts_sql_folds_chunks_into_sources_and_canon() -> None:
    """The SQL constant must reference both source_documents and
    source_chunks for both the sources and canon facet counts. This
    locks in the fix at the SQL string level."""
    from app.services.search import _COUNTS_SQL

    sql = _COUNTS_SQL
    # The "sources" facet should be one of the two SQL chunks containing
    # both source_documents and source_chunks. Same for "canon".
    sources_block = sql.split("'sources'")[1].split("UNION ALL")[0]
    canon_block = sql.split("'canon'")[1]
    assert "source_documents" in sources_block
    assert "source_chunks" in sources_block
    assert "source_documents" in canon_block
    assert "source_chunks" in canon_block


def test_search_route_invokes_orchestrator(monkeypatch) -> None:
    """Smoke-test the route shim itself via TestClient + dependency override."""
    from collections.abc import Generator

    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session, sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db import get_db
    from app.main import app

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionTesting = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def override_db() -> Generator[Session, None, None]:
        d = SessionTesting()
        try:
            yield d
        finally:
            d.close()

    app.dependency_overrides[get_db] = override_db
    captured = {}

    def fake_run_search(_db, **kwargs):
        captured.update(kwargs)
        return {
            "results": [{
                "id": 1, "type": "task", "title": "Hi", "snippet": "<mark>hi</mark>",
                "relevance": 0.5, "url": "/tasks?selected=1", "metadata": {"status": "in_progress"}
            }],
            "total": 1,
            "type_counts": {"tasks": 1},
            "mode": "keyword",
        }

    with patch.object(search_module, "search", fake_run_search):
        client = TestClient(app)
        resp = client.get("/search", params={"q": "hello", "type": "tasks", "limit": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["query"] == "hello"
    assert body["mode"] == "keyword"
    assert body["type_filter"] == "tasks"
    assert body["total"] == 1
    assert body["results"][0]["title"] == "Hi"
    assert captured["query"] == "hello"
    assert captured["type_filter"] == "tasks"
    assert captured["limit"] == 5

    app.dependency_overrides.clear()
