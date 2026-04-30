"""Unified source ingestion pipeline.

The HTTP upload route persists the file and creates a SourceDocument with
processing_status="queued", then schedules ``process_source`` to run as a
FastAPI BackgroundTask. ``process_source`` routes by file kind (PDF /
audio / video / text|docx), updates progress fields incrementally, and
runs the chunk + index pipeline at the end.

Each PDF page-batch is run inside a short-lived ThreadPoolExecutor so a
single hung batch (corrupt page, infinite recursion in pypdf) cannot
stall the whole job — the offending batch is recorded as a partial
failure and the next batch proceeds.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path

from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.chunking import chunk_text
from app.config import get_settings
from app import db as db_module
from app.models import SourceDocument
from app.repositories import (
    create_source_chunk,
    get_source_document_by_id,
)
from app.services.audio_utils import file_kind
from app.services.transcription import (
    TranscriptionError,
    TranscriptionResult,
    get_transcription_provider,
)
from app.source_extraction import extract_text

logger = logging.getLogger(__name__)

PAGES_PER_BATCH = 10


# ─── Public entry points ─────────────────────────────────────────────


def queue_source_processing(source_id: int) -> None:
    """Run the pipeline in a background thread. Safe to call from a route.

    Opens its own DB session because the request-scoped session is closed
    by the time the BackgroundTask fires. Tests can install a different
    factory by monkeypatching ``app.db.SessionLocal``.
    """
    db = db_module.SessionLocal()
    try:
        process_source(db, source_id)
    finally:
        db.close()


def process_source(db: Session, source_id: int) -> SourceDocument | None:
    """Route to the right processor based on file kind. Synchronous."""
    source = get_source_document_by_id(db, source_id)
    if source is None:
        logger.warning("process_source: source not found", extra={"context": {"source_id": source_id}})
        return None

    path = Path(source.source_path)
    if not path.exists():
        _mark_failed(db, source, f"source file missing at {path}")
        return source

    kind = file_kind(path)
    started = time.monotonic()
    overall_timeout = get_settings().processing_overall_timeout_seconds

    try:
        if kind == "pdf":
            _process_pdf(db, source, path, started=started, overall_timeout=overall_timeout)
        elif kind in ("audio", "video"):
            _process_media(db, source, path)
        elif kind == "text":
            _process_text(db, source, path)
        else:
            _mark_failed(db, source, f"unsupported file type: {path.suffix}")
    except Exception as exc:  # last-resort catch so background never crashes silently
        logger.exception("process_source: unhandled error", extra={"context": {"source_id": source_id}})
        _mark_failed(db, source, f"unhandled error: {exc}")

    db.refresh(source)
    _emit_processing_audit(db, source)
    _maybe_auto_extract(db, source)
    return source


def _emit_processing_audit(db: Session, source: SourceDocument) -> None:
    """Record one audit event reflecting the terminal processing state."""
    from app.services.audit import log_event

    status = source.processing_status
    if status not in ("complete", "partial", "failed"):
        return
    action = "source_failed" if status == "failed" else "source_processed"
    log_event(
        db,
        entity_type="source",
        entity_id=source.id,
        action=action,
        metadata={
            "source_type": source.source_type,
            "processing_status": status,
            "pages_total": source.pages_total,
            "pages_processed": source.pages_processed,
            "error": (source.processing_error or "")[:200] if status == "failed" else None,
        },
    )
    db.commit()


# ─── PDF ─────────────────────────────────────────────────────────────


def _process_pdf(
    db: Session,
    source: SourceDocument,
    path: Path,
    *,
    started: float,
    overall_timeout: int,
) -> None:
    settings = get_settings()
    batch_timeout = settings.pdf_batch_timeout_seconds

    reader = PdfReader(str(path))
    total_pages = len(reader.pages)
    source.processing_status = "processing"
    source.pages_total = total_pages
    source.pages_processed = 0
    source.processing_error = None
    db.commit()

    full_text_parts: list[str] = []
    chunk_index = 0
    pages_done = 0
    batch_failures: list[str] = []
    timed_out = False

    for batch_start in range(0, total_pages, PAGES_PER_BATCH):
        if time.monotonic() - started > overall_timeout:
            timed_out = True
            batch_failures.append(
                f"overall timeout exceeded at page {pages_done}/{total_pages}"
            )
            break

        batch_end = min(batch_start + PAGES_PER_BATCH, total_pages)
        try:
            batch_text = _extract_pdf_batch_with_timeout(
                reader, batch_start, batch_end, batch_timeout
            )
        except FutureTimeoutError:
            batch_failures.append(
                f"batch {batch_start}-{batch_end} timed out after {batch_timeout}s"
            )
            pages_done = batch_end
            source.pages_processed = pages_done
            db.commit()
            continue
        except Exception as exc:  # pypdf can raise a wide variety on corrupt pages
            batch_failures.append(f"batch {batch_start}-{batch_end} failed: {exc}")
            pages_done = batch_end
            source.pages_processed = pages_done
            db.commit()
            continue

        full_text_parts.append(batch_text)
        for chunk in chunk_text(batch_text):
            create_source_chunk(
                db,
                {
                    "source_document_id": source.id,
                    "chunk_index": chunk_index,
                    "chunk_text": chunk,
                    "embedding": None,
                },
            )
            chunk_index += 1

        pages_done = batch_end
        source.pages_processed = pages_done
        db.commit()
        logger.info(
            "PDF batch committed",
            extra={
                "event": "pdf_batch_committed",
                "context": {
                    "source_id": source.id,
                    "pages_done": pages_done,
                    "pages_total": total_pages,
                    "chunks_so_far": chunk_index,
                },
            },
        )

    full_text = "\n".join(full_text_parts).strip()
    source.extracted_text = full_text
    if timed_out or batch_failures:
        source.processing_status = "partial" if chunk_index > 0 else "failed"
        source.processing_error = "; ".join(batch_failures)[:4000]
    else:
        source.processing_status = "complete"
        source.processing_error = None
    db.commit()


def _extract_pdf_batch_with_timeout(
    reader: PdfReader, start: int, end: int, timeout: int
) -> str:
    """Run the batch in a worker thread so a hung page can be abandoned.

    PdfReader pages are 0-indexed. Each page is extracted in isolation so
    one bad page cannot poison the whole batch.
    """
    def _run() -> str:
        page_texts: list[str] = []
        for i in range(start, end):
            try:
                page_texts.append(reader.pages[i].extract_text() or "")
            except Exception:
                logger.warning("page %d extract failed", i, exc_info=True)
                page_texts.append("")
        return "\n".join(page_texts)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_run)
        return future.result(timeout=timeout)


# ─── Audio / Video ───────────────────────────────────────────────────


def _process_media(db: Session, source: SourceDocument, path: Path) -> None:
    source.processing_status = "processing"
    source.processing_error = None
    db.commit()

    provider = get_transcription_provider()
    try:
        result: TranscriptionResult = provider.transcribe(path)
    except TranscriptionError as exc:
        _mark_failed(db, source, f"transcription failed: {exc}")
        return
    except Exception as exc:
        _mark_failed(db, source, f"transcription failed: {exc}")
        return

    settings = get_settings()
    if result.duration_seconds > settings.max_audio_duration_seconds:
        _mark_failed(
            db,
            source,
            f"audio duration {result.duration_seconds:.0f}s exceeds limit "
            f"{settings.max_audio_duration_seconds}s",
        )
        return

    source.extracted_text = result.full_text
    source.processing_metadata = {
        "duration_seconds": result.duration_seconds,
        "confidence": result.confidence,
        "segments": result.segments_as_dicts(),
    }
    chunk_index = 0
    for chunk in chunk_text(result.full_text):
        create_source_chunk(
            db,
            {
                "source_document_id": source.id,
                "chunk_index": chunk_index,
                "chunk_text": chunk,
                "embedding": None,
            },
        )
        chunk_index += 1
    source.processing_status = "complete"
    db.commit()


# ─── Text / docx ─────────────────────────────────────────────────────


def _process_text(db: Session, source: SourceDocument, path: Path) -> None:
    source.processing_status = "processing"
    source.processing_error = None
    db.commit()

    text = extract_text(path)
    source.extracted_text = text
    chunk_index = 0
    for chunk in chunk_text(text):
        create_source_chunk(
            db,
            {
                "source_document_id": source.id,
                "chunk_index": chunk_index,
                "chunk_text": chunk,
                "embedding": None,
            },
        )
        chunk_index += 1
    source.processing_status = "complete"
    db.commit()


# ─── Helpers ─────────────────────────────────────────────────────────


def _maybe_auto_extract(db: Session, source: SourceDocument) -> None:
    """Run task extraction after a successful ingest unless disabled.

    Canon documents are skipped — they describe standards, not action
    items. Sources that finished as ``failed`` are also skipped because
    there is nothing useful to extract from.
    """
    settings = get_settings()
    if not settings.auto_extract_tasks:
        return
    if source.processing_status not in ("complete", "partial"):
        return
    if source.source_type == "canon_doc":
        return
    if not (source.extracted_text or "").strip():
        return

    try:
        from app.services.task_extraction import extract_task_candidates_from_source

        extract_task_candidates_from_source(db, source.id)
    except Exception:
        logger.exception(
            "auto-extraction failed",
            extra={"context": {"source_id": source.id}},
        )


def _mark_failed(db: Session, source: SourceDocument, reason: str) -> None:
    source.processing_status = "failed"
    source.processing_error = reason[:4000]
    db.commit()
    logger.error(
        "source processing failed",
        extra={"event": "source_processing_failed", "context": {"source_id": source.id, "reason": reason}},
    )


__all__ = ["process_source", "queue_source_processing"]
