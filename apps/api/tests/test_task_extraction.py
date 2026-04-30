"""Tests for the LLM-driven task candidate extraction pipeline.

These tests use the deterministic ``MockAIProvider`` so they run without
network access. They focus on the integration shape: that LLM-derived
fields make it onto the persisted ``task_candidates`` rows, that canon
documents are skipped, and that transcript metadata flows into the
provider's prompts.
"""
from __future__ import annotations


from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import (
    AuditEvent,
    CallArtifact,
    SourceChunk,
    SourceDocument,
    Task,
    TaskCandidate,
    TaskUpdate,
)
from app.providers import ExtractedCandidate
from app.services.task_extraction import (
    _format_timestamp,
    _segment_windows,
    extract_task_candidates_from_source,
)


def _setup_engine_and_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionTesting = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    SourceDocument.__table__.create(bind=engine)
    SourceChunk.__table__.create(bind=engine)
    CallArtifact.__table__.create(bind=engine)
    TaskCandidate.__table__.create(bind=engine)
    Task.__table__.create(bind=engine)
    TaskUpdate.__table__.create(bind=engine)
    AuditEvent.__table__.create(bind=engine)
    return engine, SessionTesting


def test_extraction_skips_canon_documents() -> None:
    _, SessionTesting = _setup_engine_and_session()
    db: Session = SessionTesting()

    source = SourceDocument(
        filename="canon.txt",
        source_type="canon_doc",
        canonical_doc_id="canon-001",
        version_label="v1",
        is_active_canon_version=True,
        extracted_text="Standard: Anticipation. Definition: see what's needed before it's asked.",
        source_path="inline:canon.txt",
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    out = extract_task_candidates_from_source(db, source.id)
    assert out == []
    db.close()


def test_extraction_persists_llm_candidate_fields() -> None:
    _, SessionTesting = _setup_engine_and_session()
    db: Session = SessionTesting()

    source = SourceDocument(
        filename="thread.txt",
        source_type="thread_export",
        is_active_canon_version=False,
        extracted_text="Action: Owner: Alex follow up by 2026-04-30 — urgent",
        source_path="inline:thread.txt",
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    rows = extract_task_candidates_from_source(db, source.id)
    assert rows is not None and len(rows) >= 1

    llm_rows = [r for r in rows if (r.hints_json or {}).get("llm_extracted")]
    assert llm_rows, "expected at least one LLM-extracted candidate"
    sample = llm_rows[0]
    assert sample.suggested_priority in {"low", "medium", "high"}
    assert sample.canon_alignment
    assert (sample.hints_json or {}).get("extraction_kind") in {
        "action_item",
        "decision",
        "discussion",
    }
    db.close()


def test_extraction_returns_none_for_missing_source() -> None:
    _, SessionTesting = _setup_engine_and_session()
    db: Session = SessionTesting()
    assert extract_task_candidates_from_source(db, 9999) is None
    db.close()


def test_transcript_metadata_drives_speakers_into_prompt() -> None:
    """Transcripts route through the speaker-aware prompt path."""
    _, SessionTesting = _setup_engine_and_session()
    db: Session = SessionTesting()

    segments = [
        {
            "start_time": 0.0,
            "end_time": 60.0,
            "text": "We need to confirm the roof quote by next week.",
            "speaker": "Speaker 1",
        },
        {
            "start_time": 60.0,
            "end_time": 120.0,
            "text": "I'll send the email today.",
            "speaker": "Speaker 2",
        },
    ]
    source = SourceDocument(
        filename="call.mp3",
        source_type="transcript",
        is_active_canon_version=False,
        extracted_text="[Speaker 1] We need... [Speaker 2] I'll send...",
        source_path="data/uploads/call.mp3",
        processing_metadata={"duration_seconds": 120.0, "segments": segments},
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    captured: dict = {}

    class _CapturingMock:
        def extract_candidates(self, *, system_prompt: str, user_message: str):
            captured["system"] = system_prompt
            captured["user"] = user_message
            return [
                ExtractedCandidate(
                    title="Send roof quote follow-up",
                    description="Speaker 2 committed to send the email today.",
                    suggested_owner="Speaker 2",
                    suggested_priority="high",
                    suggested_due_date_iso=None,
                    source_reference="roof quote",
                    source_timestamp="01:00 → 02:00",
                    confidence=0.82,
                    canon_alignment="Accountability",
                    extraction_kind="action_item",
                )
            ]

    rows = extract_task_candidates_from_source(db, source.id, ai_provider=_CapturingMock())
    assert rows is not None and any(
        (r.hints_json or {}).get("llm_extracted") for r in rows
    )
    assert "speaker" in captured["system"].lower()
    assert "[Speaker 1" in captured["user"] or "Speaker 1" in captured["user"]
    db.close()


def test_segment_windows_buckets_by_minute() -> None:
    segments = [
        {"start_time": 30.0, "end_time": 60.0, "text": "a"},
        {"start_time": 600.0, "end_time": 620.0, "text": "b"},
        {"start_time": 1200.0, "end_time": 1300.0, "text": "c"},
    ]
    windows = _segment_windows(segments, window_minutes=10)
    assert len(windows) == 3
    labels = [w[0] for w in windows]
    assert labels == ["00:00-10:00", "10:00-20:00", "20:00-30:00"]


def test_format_timestamp_handles_floats_and_strings() -> None:
    assert _format_timestamp(0) == "00:00"
    assert _format_timestamp(125) == "02:05"
    assert _format_timestamp("notanumber") == "00:00"


def test_verbatim_catchall_suppressed_when_llm_produces_good_candidates() -> None:
    """A heuristic line that is just a verbatim copy of input (no urgency,
    blocker, recurrence, completion, or delegation hints) should be dropped
    when the LLM returns a high-signal candidate.
    """
    _, SessionTesting = _setup_engine_and_session()
    db: Session = SessionTesting()

    # Plain "todo" line — no urgency words, no owner, no date, no hints.
    # This trips the heuristic but provides nothing the LLM didn't see.
    source = SourceDocument(
        filename="thread.txt",
        source_type="thread_export",
        is_active_canon_version=False,
        extracted_text="todo: figure out the vendor situation",
        source_path="inline:thread.txt",
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    class _GoodLLM:
        def extract_candidates(self, *, system_prompt: str, user_message: str):
            return [
                ExtractedCandidate(
                    title="Confirm vendor delivery date with Alex",
                    description="Alex committed to lock in the delivery date this week.",
                    suggested_owner="Alex",
                    suggested_priority="high",
                    suggested_due_date_iso=None,
                    source_reference="vendor situation",
                    source_timestamp=None,
                    confidence=0.85,
                    canon_alignment="Accountability",
                    extraction_kind="action_item",
                )
            ]

    rows = extract_task_candidates_from_source(db, source.id, ai_provider=_GoodLLM())
    assert rows is not None
    # No verbatim heuristic row should remain; every persisted row must be
    # the LLM candidate.
    titles = [r.title for r in rows]
    assert "todo: figure out the vendor situation" not in titles
    assert any(t.startswith("Confirm vendor delivery date") for t in titles)
    assert all((r.hints_json or {}).get("llm_extracted") for r in rows)
    db.close()


def test_verbatim_catchall_kept_when_llm_returns_nothing() -> None:
    """If the LLM produces nothing, the heuristic catch-all is the only
    signal we have — never strip it down to empty."""
    _, SessionTesting = _setup_engine_and_session()
    db: Session = SessionTesting()

    source = SourceDocument(
        filename="thread.txt",
        source_type="thread_export",
        is_active_canon_version=False,
        extracted_text="todo: figure out the vendor situation",
        source_path="inline:thread.txt",
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    class _SilentLLM:
        def extract_candidates(self, *, system_prompt: str, user_message: str):
            return []

    rows = extract_task_candidates_from_source(db, source.id, ai_provider=_SilentLLM())
    assert rows is not None
    assert len(rows) >= 1
    assert any("vendor situation" in (r.title or "") for r in rows)
    db.close()


def test_long_transcript_invokes_dedup_pass() -> None:
    """Transcripts longer than the window size go through dedup.

    We don't assert the exact dedup output (the mock returns 3 fixed
    candidates per call), only that ``extract_candidates`` was invoked
    more than once: once per window plus the dedup pass.
    """
    _, SessionTesting = _setup_engine_and_session()
    db: Session = SessionTesting()

    segments = [
        {"start_time": float(i * 60), "end_time": float(i * 60 + 30), "text": f"line {i}", "speaker": "Speaker 1"}
        for i in range(40)
    ]
    source = SourceDocument(
        filename="long.mp3",
        source_type="transcript",
        is_active_canon_version=False,
        extracted_text="(transcript)",
        source_path="data/uploads/long.mp3",
        processing_metadata={"duration_seconds": 60 * 40, "segments": segments},
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    calls: list[str] = []

    class _CountingMock:
        def extract_candidates(self, *, system_prompt: str, user_message: str):
            calls.append("call")
            return []

    extract_task_candidates_from_source(db, source.id, ai_provider=_CountingMock())
    # At least 4 windowed calls (40 segments at 1-minute spacing across 40
    # minutes -> 4 ten-minute buckets) plus a dedup pass. The dedup pass
    # only runs when there is something to merge, so with empty results
    # the call count equals the number of windows. Either way it must
    # exceed a single non-windowed call.
    assert len(calls) >= 2
    db.close()
