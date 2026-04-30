"""Unified search across tasks, updates, sub-tasks, obstacles, sources,
source chunks, reviews, and canon documents.

Two modes:

- ``keyword`` (default): Postgres FTS — every searchable table has a
  ``search_vector`` STORED GENERATED tsvector column with a GIN index
  (migration 0017). Per-type queries use ``websearch_to_tsquery`` for
  user-friendly syntax (quotes, OR, leading ``-``) and ``ts_rank_cd``
  for ranking. Snippets come from ``ts_headline`` with ``<mark>`` tags.

- ``semantic``: query is embedded with the configured EmbeddingsAdapter
  and matched against ``source_chunks.embedding`` via pgvector cosine
  distance (``<=>``). Results are chunk-scoped; the joined source
  document carries the display title and metadata.

The route layer owns the unified ``SearchResult`` envelope; this module
returns lists of dicts shaped for that envelope.
"""
from __future__ import annotations

import logging
from typing import Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.providers import MockEmbeddingsAdapter

logger = logging.getLogger(__name__)

TypeFilter = Literal["all", "tasks", "sources", "reviews", "canon"]
Mode = Literal["keyword", "semantic"]

MAX_LIMIT = 100
DEFAULT_LIMIT = 20

HEADLINE_OPTS = (
    "StartSel=<mark>,StopSel=</mark>,"
    "MaxWords=24,MinWords=10,ShortWord=3,MaxFragments=1"
)


def search(
    db: Session,
    *,
    query: str,
    type_filter: TypeFilter = "all",
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    mode: Mode = "keyword",
) -> dict:
    """Run a unified search and return ``{results, total, type_counts, mode}``.

    ``total`` is the count for the active filter; ``type_counts`` is the
    per-type breakdown across the whole index for the same query so the
    frontend can render sidebar facets.
    """
    q = (query or "").strip()
    if not q:
        return {"results": [], "total": 0, "type_counts": {}, "mode": mode}

    safe_limit = max(1, min(int(limit), MAX_LIMIT))
    safe_offset = max(0, int(offset))

    if mode == "semantic":
        results = _semantic_search(db, query=q, limit=safe_limit, offset=safe_offset)
        return {
            "results": results,
            "total": len(results),
            "type_counts": {"source_chunk": len(results)},
            "mode": "semantic",
        }

    type_counts = _count_by_type(db, q)
    runners = _runners_for_filter(type_filter)
    raw: list[dict] = []
    for fn in runners:
        try:
            raw.extend(fn(db, q, safe_limit + safe_offset))
        except Exception:
            logger.exception("search runner failed", extra={"context": {"runner": fn.__name__}})

    raw.sort(key=lambda r: r["relevance"], reverse=True)
    total = len(raw)
    paged = raw[safe_offset : safe_offset + safe_limit]
    return {
        "results": paged,
        "total": total,
        "type_counts": type_counts,
        "mode": "keyword",
    }


# ─── Keyword runners ────────────────────────────────────────────────


def _runners_for_filter(type_filter: TypeFilter):
    if type_filter == "tasks":
        return [_search_tasks, _search_task_updates, _search_sub_tasks, _search_obstacles]
    if type_filter == "sources":
        return [_search_sources, _search_source_chunks]
    if type_filter == "reviews":
        return [_search_reviews]
    if type_filter == "canon":
        return [_search_canon]
    return [
        _search_tasks,
        _search_task_updates,
        _search_sub_tasks,
        _search_obstacles,
        _search_sources,
        _search_source_chunks,
        _search_reviews,
        _search_canon,
    ]


def _search_tasks(db: Session, q: str, limit: int) -> list[dict]:
    rows = db.execute(
        text(
            f"""
            SELECT id, title, status, owner_name, priority,
              ts_headline('english',
                coalesce(description, '') || ' ' || coalesce(objective, ''),
                websearch_to_tsquery('english', :q),
                '{HEADLINE_OPTS}') AS snippet,
              ts_rank_cd(search_vector, websearch_to_tsquery('english', :q)) AS rank
            FROM tasks
            WHERE search_vector @@ websearch_to_tsquery('english', :q)
            ORDER BY rank DESC
            LIMIT :limit
            """
        ),
        {"q": q, "limit": limit},
    ).mappings().all()
    return [
        {
            "id": r["id"],
            "type": "task",
            "title": r["title"],
            "snippet": r["snippet"] or "",
            "relevance": float(r["rank"]),
            "url": f"/tasks?selected={r['id']}",
            "metadata": {
                "status": r["status"],
                "owner_name": r["owner_name"],
                "priority": r["priority"],
            },
        }
        for r in rows
    ]


def _search_task_updates(db: Session, q: str, limit: int) -> list[dict]:
    rows = db.execute(
        text(
            f"""
            SELECT tu.id, tu.task_id, tu.update_type, tu.summary, tu.created_at,
              t.title AS task_title,
              ts_headline('english',
                coalesce(tu.what_happened, '') || ' ' || coalesce(tu.next_step, ''),
                websearch_to_tsquery('english', :q),
                '{HEADLINE_OPTS}') AS snippet,
              ts_rank_cd(tu.search_vector, websearch_to_tsquery('english', :q)) AS rank
            FROM task_updates tu
            JOIN tasks t ON t.id = tu.task_id
            WHERE tu.search_vector @@ websearch_to_tsquery('english', :q)
            ORDER BY rank DESC
            LIMIT :limit
            """
        ),
        {"q": q, "limit": limit},
    ).mappings().all()
    return [
        {
            "id": r["id"],
            "type": "task_update",
            "title": f"Update on: {r['task_title']}",
            "snippet": r["snippet"] or r["summary"] or "",
            "relevance": float(r["rank"]),
            "url": f"/tasks?selected={r['task_id']}",
            "metadata": {
                "task_id": r["task_id"],
                "update_type": r["update_type"],
            },
        }
        for r in rows
    ]


def _search_sub_tasks(db: Session, q: str, limit: int) -> list[dict]:
    rows = db.execute(
        text(
            f"""
            SELECT s.id, s.parent_task_id, s.title, s.status, s.canon_reference,
              t.title AS task_title,
              ts_headline('english', coalesce(s.description, ''),
                websearch_to_tsquery('english', :q),
                '{HEADLINE_OPTS}') AS snippet,
              ts_rank_cd(s.search_vector, websearch_to_tsquery('english', :q)) AS rank
            FROM sub_tasks s
            JOIN tasks t ON t.id = s.parent_task_id
            WHERE s.search_vector @@ websearch_to_tsquery('english', :q)
            ORDER BY rank DESC
            LIMIT :limit
            """
        ),
        {"q": q, "limit": limit},
    ).mappings().all()
    return [
        {
            "id": r["id"],
            "type": "sub_task",
            "title": r["title"],
            "snippet": r["snippet"] or "",
            "relevance": float(r["rank"]),
            "url": f"/tasks?selected={r['parent_task_id']}",
            "metadata": {
                "parent_task_id": r["parent_task_id"],
                "parent_task_title": r["task_title"],
                "status": r["status"],
                "canon_reference": r["canon_reference"],
            },
        }
        for r in rows
    ]


def _search_obstacles(db: Session, q: str, limit: int) -> list[dict]:
    rows = db.execute(
        text(
            f"""
            SELECT o.id, o.task_id, o.description, o.status, t.title AS task_title,
              ts_headline('english',
                coalesce(o.description, '') || ' ' || coalesce(o.impact, '')
                  || ' ' || coalesce(o.resolution_notes, ''),
                websearch_to_tsquery('english', :q),
                '{HEADLINE_OPTS}') AS snippet,
              ts_rank_cd(o.search_vector, websearch_to_tsquery('english', :q)) AS rank
            FROM obstacles o
            JOIN tasks t ON t.id = o.task_id
            WHERE o.search_vector @@ websearch_to_tsquery('english', :q)
            ORDER BY rank DESC
            LIMIT :limit
            """
        ),
        {"q": q, "limit": limit},
    ).mappings().all()
    return [
        {
            "id": r["id"],
            "type": "obstacle",
            "title": (r["description"] or "")[:80],
            "snippet": r["snippet"] or "",
            "relevance": float(r["rank"]),
            "url": f"/tasks?selected={r['task_id']}",
            "metadata": {
                "task_id": r["task_id"],
                "task_title": r["task_title"],
                "status": r["status"],
            },
        }
        for r in rows
    ]


def _search_sources(db: Session, q: str, limit: int) -> list[dict]:
    rows = db.execute(
        text(
            f"""
            SELECT id, filename, source_type, canonical_doc_id, version_label,
              is_active_canon_version, processing_status,
              ts_headline('english',
                coalesce(filename, '') || ' '
                  || coalesce(canonical_doc_id, '') || ' '
                  || coalesce(version_label, ''),
                websearch_to_tsquery('english', :q),
                '{HEADLINE_OPTS}') AS snippet,
              ts_rank_cd(search_vector, websearch_to_tsquery('english', :q)) AS rank
            FROM source_documents
            WHERE source_type <> 'canon_doc'
              AND search_vector @@ websearch_to_tsquery('english', :q)
            ORDER BY rank DESC
            LIMIT :limit
            """
        ),
        {"q": q, "limit": limit},
    ).mappings().all()
    return [
        {
            "id": r["id"],
            "type": "source",
            "title": r["filename"],
            "snippet": r["snippet"] or "",
            "relevance": float(r["rank"]),
            "url": f"/sources?source_id={r['id']}",
            "metadata": {
                "source_type": r["source_type"],
                "processing_status": r["processing_status"],
                "canonical_doc_id": r["canonical_doc_id"],
            },
        }
        for r in rows
    ]


def _search_source_chunks(db: Session, q: str, limit: int) -> list[dict]:
    """Chunk-level matches inside non-canon documents; deduped per source."""
    rows = db.execute(
        text(
            f"""
            SELECT DISTINCT ON (sc.source_document_id)
              sc.id AS chunk_id, sc.source_document_id, sc.chunk_index,
              sd.filename, sd.source_type, sd.processing_status,
              ts_headline('english', sc.chunk_text,
                websearch_to_tsquery('english', :q),
                '{HEADLINE_OPTS}') AS snippet,
              ts_rank_cd(sc.search_vector, websearch_to_tsquery('english', :q)) AS rank
            FROM source_chunks sc
            JOIN source_documents sd ON sd.id = sc.source_document_id
            WHERE sd.source_type <> 'canon_doc'
              AND sc.search_vector @@ websearch_to_tsquery('english', :q)
            ORDER BY sc.source_document_id, rank DESC
            LIMIT :limit
            """
        ),
        {"q": q, "limit": limit},
    ).mappings().all()
    return [
        {
            "id": r["source_document_id"],
            "type": "source_chunk",
            "title": r["filename"],
            "snippet": r["snippet"] or "",
            "relevance": float(r["rank"]),
            "url": f"/sources?source_id={r['source_document_id']}",
            "metadata": {
                "source_type": r["source_type"],
                "chunk_index": r["chunk_index"],
            },
        }
        for r in rows
    ]


def _search_reviews(db: Session, q: str, limit: int) -> list[dict]:
    rows = db.execute(
        text(
            f"""
            SELECT r.id, r.task_id, r.reviewer, r.created_at,
              t.title AS task_title,
              ts_headline('english',
                coalesce(r.notes, '') || ' ' || coalesce(r.action_items, ''),
                websearch_to_tsquery('english', :q),
                '{HEADLINE_OPTS}') AS snippet,
              ts_rank_cd(r.search_vector, websearch_to_tsquery('english', :q)) AS rank
            FROM review_sessions r
            LEFT JOIN tasks t ON t.id = r.task_id
            WHERE r.search_vector @@ websearch_to_tsquery('english', :q)
            ORDER BY rank DESC
            LIMIT :limit
            """
        ),
        {"q": q, "limit": limit},
    ).mappings().all()
    return [
        {
            "id": r["id"],
            "type": "review",
            "title": f"Review by {r['reviewer']}"
            + (f" — {r['task_title']}" if r["task_title"] else ""),
            "snippet": r["snippet"] or "",
            "relevance": float(r["rank"]),
            "url": "/review",
            "metadata": {
                "task_id": r["task_id"],
                "reviewer": r["reviewer"],
            },
        }
        for r in rows
    ]


def _search_canon(db: Session, q: str, limit: int) -> list[dict]:
    """Search canon documents via filename/version + their chunks."""
    rows = db.execute(
        text(
            f"""
            SELECT DISTINCT ON (sd.id)
              sd.id, sd.filename, sd.canonical_doc_id, sd.version_label,
              sd.is_active_canon_version,
              ts_headline('english',
                coalesce(sd.filename, '') || ' '
                  || coalesce(sd.canonical_doc_id, '') || ' '
                  || coalesce(sd.version_label, '') || ' '
                  || coalesce(sc.chunk_text, ''),
                websearch_to_tsquery('english', :q),
                '{HEADLINE_OPTS}') AS snippet,
              GREATEST(
                ts_rank_cd(sd.search_vector, websearch_to_tsquery('english', :q)),
                COALESCE(ts_rank_cd(sc.search_vector, websearch_to_tsquery('english', :q)), 0)
              ) AS rank
            FROM source_documents sd
            LEFT JOIN source_chunks sc ON sc.source_document_id = sd.id
              AND sc.search_vector @@ websearch_to_tsquery('english', :q)
            WHERE sd.source_type = 'canon_doc'
              AND (sd.search_vector @@ websearch_to_tsquery('english', :q)
                   OR sc.search_vector @@ websearch_to_tsquery('english', :q))
            ORDER BY sd.id, rank DESC
            LIMIT :limit
            """
        ),
        {"q": q, "limit": limit},
    ).mappings().all()
    return [
        {
            "id": r["id"],
            "type": "canon",
            "title": r["filename"],
            "snippet": r["snippet"] or "",
            "relevance": float(r["rank"]),
            "url": f"/sources?source_id={r['id']}",
            "metadata": {
                "canonical_doc_id": r["canonical_doc_id"],
                "version_label": r["version_label"],
                "active": r["is_active_canon_version"],
            },
        }
        for r in rows
    ]


_COUNTS_SQL = """
SELECT 'tasks' AS type, COUNT(*) AS n FROM tasks
  WHERE search_vector @@ websearch_to_tsquery('english', :q)
UNION ALL
SELECT 'task_updates', COUNT(*) FROM task_updates
  WHERE search_vector @@ websearch_to_tsquery('english', :q)
UNION ALL
SELECT 'sub_tasks', COUNT(*) FROM sub_tasks
  WHERE search_vector @@ websearch_to_tsquery('english', :q)
UNION ALL
SELECT 'obstacles', COUNT(*) FROM obstacles
  WHERE search_vector @@ websearch_to_tsquery('english', :q)
UNION ALL
SELECT 'reviews', COUNT(*) FROM review_sessions
  WHERE search_vector @@ websearch_to_tsquery('english', :q)
UNION ALL
-- Sources facet folds document-level + chunk-level matches into a
-- single per-document count. UNION (not UNION ALL) deduplicates the
-- doc id when both the document and one of its chunks match.
SELECT 'sources', COUNT(*) FROM (
    SELECT id FROM source_documents
      WHERE source_type <> 'canon_doc'
        AND search_vector @@ websearch_to_tsquery('english', :q)
    UNION
    SELECT sc.source_document_id FROM source_chunks sc
      JOIN source_documents sd ON sd.id = sc.source_document_id
      WHERE sd.source_type <> 'canon_doc'
        AND sc.search_vector @@ websearch_to_tsquery('english', :q)
) AS sources_distinct
UNION ALL
-- Canon facet has the same fold so chunk-level matches inside a canon
-- doc bump the count too.
SELECT 'canon', COUNT(*) FROM (
    SELECT id FROM source_documents
      WHERE source_type = 'canon_doc'
        AND search_vector @@ websearch_to_tsquery('english', :q)
    UNION
    SELECT sc.source_document_id FROM source_chunks sc
      JOIN source_documents sd ON sd.id = sc.source_document_id
      WHERE sd.source_type = 'canon_doc'
        AND sc.search_vector @@ websearch_to_tsquery('english', :q)
) AS canon_distinct
"""


def _count_by_type(db: Session, q: str) -> dict[str, int]:
    """One-shot count per logical type so the UI can render facet counts.

    The ``sources`` and ``canon`` buckets count distinct source documents
    that match either at the document level or at any chunk level — so a
    query whose only hits are deep inside the chunk text still bumps the
    facet count. (See ``_COUNTS_SQL`` above.)
    """
    counts = db.execute(text(_COUNTS_SQL), {"q": q}).mappings().all()
    return {row["type"]: int(row["n"]) for row in counts}


# ─── Semantic mode ──────────────────────────────────────────────────


def _semantic_search(
    db: Session, *, query: str, limit: int, offset: int
) -> list[dict]:
    """Embed the query, find nearest source_chunks via pgvector cosine.

    Falls back to keyword sources search if pgvector or any embeddings
    are missing, so the route never 500s when the index is empty.
    """
    embedder = MockEmbeddingsAdapter()
    embedding = embedder.embed_text(query)
    embedding_lit = "[" + ",".join(f"{v:.6f}" for v in embedding) + "]"

    try:
        rows = db.execute(
            text(
                """
                SELECT sc.id AS chunk_id, sc.source_document_id, sc.chunk_index,
                  sc.chunk_text, sd.filename, sd.source_type, sd.processing_status,
                  1 - (sc.embedding <=> CAST(:embedding AS vector)) AS similarity
                FROM source_chunks sc
                JOIN source_documents sd ON sd.id = sc.source_document_id
                WHERE sc.embedding IS NOT NULL
                ORDER BY sc.embedding <=> CAST(:embedding AS vector)
                LIMIT :limit OFFSET :offset
                """
            ),
            {"embedding": embedding_lit, "limit": limit, "offset": offset},
        ).mappings().all()
    except Exception:
        logger.exception("semantic search failed")
        return []

    return [
        {
            "id": r["source_document_id"],
            "type": "source_chunk",
            "title": r["filename"],
            "snippet": (r["chunk_text"] or "")[:240],
            "relevance": float(r["similarity"]),
            "url": f"/sources?source_id={r['source_document_id']}",
            "metadata": {
                "source_type": r["source_type"],
                "chunk_index": r["chunk_index"],
                "similarity": float(r["similarity"]),
            },
        }
        for r in rows
    ]


__all__ = ["search", "TypeFilter", "Mode", "MAX_LIMIT", "DEFAULT_LIMIT"]
