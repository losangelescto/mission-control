"""End-to-end integration flows and edge cases (Phase 2 Day 4).

These exercise the full recommendation / sub-task / obstacle lifecycles
against the mock provider — no network, no real API key required.
"""
from collections.abc import Generator
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.main import app
from app.models import (
    AuditEvent,
    Blocker,
    Delegation,
    Obstacle,
    Recommendation,
    ReviewSession,
    SourceChunk,
    SourceDocument,
    SubTask,
    Task,
    TaskUpdate,
)


# ─── Shared fixtures ────────────────────────────────────────────────────


def _build_test_db() -> sessionmaker:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    for model in (
        SourceDocument,
        SourceChunk,
        Task,
        TaskUpdate,
        Blocker,
        Delegation,
        ReviewSession,
        Recommendation,
        SubTask,
        Obstacle,
        AuditEvent,
    ):
        model.__table__.create(bind=engine)
    return TestingSessionLocal


def _override_db(TestingSessionLocal: sessionmaker) -> None:
    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db


def _create_task(client: TestClient, **overrides) -> int:  # type: ignore[no-untyped-def]
    payload = {
        "title": "Integration task",
        "description": "Walk the inbound resident through the amenity reservation flow.",
        "objective": "Make it easy",
        "standard": "Emotional Intelligence",
        "status": "up_next",
        "priority": "high",
        "owner_name": "alex",
        "assigner_name": "jordan",
        "due_at": None,
        "source_confidence": 0.85,
    }
    payload.update(overrides)
    r = client.post("/tasks", json=payload)
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ─── 1a. Full recommendation flow with updates and blocker ──────────────


def test_full_recommendation_flow_updates_blocker_and_unblock() -> None:
    _override_db(_build_test_db())
    client = TestClient(app)
    tid = _create_task(client)

    # Add three narrative updates so the context assembler has history.
    update_summaries = [
        "Tried the current amenity flow — 4 taps to book, residents dropped off.",
        "Drafted a 2-tap alternative with the UX team.",
        "Scheduled a Thursday walk-through with two residents for feedback.",
    ]
    for s in update_summaries:
        r = client.post(
            f"/tasks/{tid}/updates",
            json={
                "update_type": "note",
                "summary": s,
                "what_happened": "",
                "options_considered": "",
                "steps_taken": "",
                "next_step": "",
                "created_by": "alex",
            },
        )
        assert r.status_code == 201

    # Standard-mode recommendation — should include update count.
    r_std = client.post(f"/tasks/{tid}/recommendation")
    assert r_std.status_code == 200
    body_std = r_std.json()
    assert body_std["recommendation_type"] == "standard"
    assert body_std["recommendation_context"]["updates_included"] == 3
    assert body_std["recommendation_context"]["blocker_active"] is False
    rec_id_standard = body_std["id"]

    # Transition to blocked via the existing block endpoint.
    r_block = client.post(
        f"/tasks/{tid}/block",
        json={
            "blocker_type": "dependency",
            "blocker_reason": "UX team unavailable this week",
            "severity": "high",
        },
    )
    assert r_block.status_code == 200
    assert r_block.json()["status"] == "blocked"

    # Unblock-mode recommendation — different shape and different row.
    r_ub = client.post(f"/tasks/{tid}/recommendation")
    assert r_ub.status_code == 200
    body_ub = r_ub.json()
    assert body_ub["recommendation_type"] == "unblock"
    assert body_ub["id"] != rec_id_standard
    assert body_ub["unblock_analysis"] is not None
    assert len(body_ub["unblock_analysis"]["alternatives"]) == 3
    assert body_ub["recommendation_context"]["blocker_active"] is True

    # Both recommendations appear in the history, newest first.
    history = client.get(f"/tasks/{tid}/recommendations").json()
    assert len(history) == 2
    assert history[0]["id"] == body_ub["id"]
    assert history[0]["recommendation_type"] == "unblock"
    assert history[1]["id"] == rec_id_standard

    # Transition back to up_next — recommendation mode follows.
    r_unblock = client.post(
        f"/tasks/{tid}/unblock",
        json={"resolution_notes": "UX picked up work on Monday", "next_status": "up_next"},
    )
    assert r_unblock.status_code == 200
    r_std2 = client.post(f"/tasks/{tid}/recommendation")
    assert r_std2.status_code == 200
    assert r_std2.json()["recommendation_type"] == "standard"

    app.dependency_overrides.clear()


# ─── 1b. Sub-task generation → save-all → progress feeds recommendation ──


def test_subtask_generation_save_complete_feeds_recommendation_context() -> None:
    _override_db(_build_test_db())
    client = TestClient(app)
    tid = _create_task(
        client,
        description=(
            "Rebuild the resident amenity reservation flow end-to-end. "
            "Current flow is 4 taps; target is 2. Include fallback copy "
            "for residents who hit an unavailable slot."
        ),
    )

    # Generate preview — mock returns 3 drafts.
    r_preview = client.post(f"/tasks/{tid}/subtasks/generate")
    assert r_preview.status_code == 200
    drafts = r_preview.json()["drafts"]
    assert 3 <= len(drafts) <= 7
    assert all(d.get("canon_reference") for d in drafts)

    # Save-all — the frontend loops; we do the same.
    created_ids: list[int] = []
    for d in drafts:
        r = client.post(f"/tasks/{tid}/subtasks", json=d)
        assert r.status_code == 201
        created_ids.append(r.json()["id"])

    # All persisted, in order.
    listing = client.get(f"/tasks/{tid}/subtasks").json()
    assert [s["id"] for s in listing] == created_ids
    assert [s["order"] for s in listing] == list(range(len(created_ids)))

    # Complete the first two.
    for sid in created_ids[:2]:
        r = client.patch(f"/subtasks/{sid}", json={"status": "completed"})
        assert r.status_code == 200
        assert r.json()["status"] == "completed"

    # Generate recommendation — context should reflect the new progress.
    r_rec = client.post(f"/tasks/{tid}/recommendation")
    assert r_rec.status_code == 200
    ctx = r_rec.json()["recommendation_context"]
    assert ctx["subtasks_total"] == len(created_ids)
    assert ctx["subtasks_completed"] == 2

    app.dependency_overrides.clear()


# ─── 1c. Obstacle analyze → resolve → subsequent recommendation ─────────


def test_obstacle_analyze_then_resolve_then_recommendation_reflects_state() -> None:
    _override_db(_build_test_db())
    client = TestClient(app)
    tid = _create_task(client)

    # Create obstacle, analyze it.
    r_ob = client.post(
        f"/tasks/{tid}/obstacles",
        json={
            "description": "Legal hasn't returned the resident waiver draft.",
            "impact": "Blocks onboarding of the Thursday tour group.",
            "identified_by": "alex",
        },
    )
    assert r_ob.status_code == 201
    oid = r_ob.json()["id"]

    r_analyze = client.post(f"/obstacles/{oid}/analyze")
    assert r_analyze.status_code == 200
    after_analyze = r_analyze.json()
    assert len(after_analyze["proposed_solutions"]) == 3
    for s in after_analyze["proposed_solutions"]:
        assert s["aligned_standard"]
        assert s["source"] == "ai_generated"

    # While obstacle is active, recommendation context shows active_obstacles=1.
    r_rec_active = client.post(f"/tasks/{tid}/recommendation")
    assert r_rec_active.status_code == 200
    assert r_rec_active.json()["recommendation_context"]["active_obstacles"] == 1

    # Resolve the obstacle.
    r_resolve = client.post(
        f"/obstacles/{oid}/resolve",
        json={"resolution_notes": "Legal signed off Tuesday; waiver attached."},
    )
    assert r_resolve.status_code == 200
    resolved = r_resolve.json()
    assert resolved["status"] == "resolved"
    assert resolved["resolved_at"] is not None
    assert resolved["resolution_notes"].startswith("Legal")

    # After resolution, active_obstacles drops to 0. The resolved obstacle
    # is still returned by the list endpoint (audit trail).
    r_rec_after = client.post(f"/tasks/{tid}/recommendation")
    assert r_rec_after.status_code == 200
    assert r_rec_after.json()["recommendation_context"]["active_obstacles"] == 0

    obstacles_after = client.get(f"/tasks/{tid}/obstacles").json()
    assert len(obstacles_after) == 1
    assert obstacles_after[0]["status"] == "resolved"

    app.dependency_overrides.clear()


# ─── 1d. Edge cases ─────────────────────────────────────────────────────


def test_empty_context_task_still_generates_recommendation() -> None:
    """Task with no updates, no sub-tasks, no obstacles — should still work."""
    _override_db(_build_test_db())
    client = TestClient(app)
    tid = _create_task(client)

    r = client.post(f"/tasks/{tid}/recommendation")
    assert r.status_code == 200
    body = r.json()
    assert body["recommendation_type"] == "standard"
    assert body["objective"]
    assert body["next_action"]
    assert len(body["viable_options"]) >= 2
    ctx = body["recommendation_context"]
    assert ctx == {
        "canon_chunks_used": 0,
        "updates_included": 0,
        "reviews_included": 0,
        "blocker_active": False,
        "subtasks_total": 0,
        "subtasks_completed": 0,
        "active_obstacles": 0,
        "resolved_obstacles_included": 0,
    }

    app.dependency_overrides.clear()


def test_short_description_still_generates_subtasks() -> None:
    """A terse task description must still produce usable sub-task drafts."""
    _override_db(_build_test_db())
    client = TestClient(app)
    tid = _create_task(client, title="Fix the fence", description="Fix the fence.")

    r = client.post(f"/tasks/{tid}/subtasks/generate")
    assert r.status_code == 200
    drafts = r.json()["drafts"]
    assert 3 <= len(drafts) <= 7
    for d in drafts:
        assert d["title"]
        assert d["canon_reference"]  # Every draft aligns to a Standard

    app.dependency_overrides.clear()


def test_reanalyze_resolved_obstacle_still_succeeds() -> None:
    """Re-running analyze on a resolved obstacle replaces the solutions.

    The obstacle stays ``resolved`` — only the advisory solutions change.
    Useful when an operator wants new alternatives for a past incident.
    """
    _override_db(_build_test_db())
    client = TestClient(app)
    tid = _create_task(client)

    ob_resp = client.post(
        f"/tasks/{tid}/obstacles",
        json={"description": "Historical incident", "impact": "for reference"},
    )
    oid = ob_resp.json()["id"]

    # Analyze + resolve.
    client.post(f"/obstacles/{oid}/analyze")
    client.post(
        f"/obstacles/{oid}/resolve",
        json={"resolution_notes": "Handled offline"},
    )

    # Mutate the solutions field so we can prove analyze replaces it.
    client.patch(f"/obstacles/{oid}", json={"status": "resolved"})

    # Re-analyze.
    r_again = client.post(f"/obstacles/{oid}/analyze")
    assert r_again.status_code == 200
    body = r_again.json()
    # Status should still be resolved — analyze only touches proposed_solutions.
    assert body["status"] == "resolved"
    assert len(body["proposed_solutions"]) == 3
    assert body["resolved_at"] is not None

    app.dependency_overrides.clear()


def test_anthropic_provider_falls_back_on_api_error() -> None:
    """When the real LLM call raises, the adapter returns a mock draft with a breadcrumb.

    We don't hit the real API — we patch the SDK client to raise.
    """
    from app.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider(api_key="sk-fake", model="claude-sonnet-4-6")
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = RuntimeError("anthropic is down")
    with patch.object(provider, "_get_client", return_value=fake_client):
        draft = provider.generate_recommendation(
            objective="o",
            standard="s",
            task_description="Something important",
            context_chunks=[
                {
                    "source_document_id": 1,
                    "source_filename": "canon-v1.txt",
                    "chunk_index": 0,
                    "chunk_text": "snippet",
                    "is_active_canon_version": True,
                }
            ],
        )

    # Mock-shaped response (echoes objective/standard)
    assert draft.objective == "o"
    assert draft.standard == "s"
    assert len(draft.viable_options) >= 2
    # Breadcrumb appended so caller sees the degradation.
    fallback_breadcrumb = next(
        (r for r in draft.source_refs if r.get("source") == "fallback_due_to_llm_error"),
        None,
    )
    assert fallback_breadcrumb is not None
    assert "anthropic is down" in fallback_breadcrumb.get("error", "")


def test_rapid_successive_requests_hit_cache() -> None:
    """Second call within the cache window returns the same recommendation id.

    slowapi keeps per-IP counters in process memory. Since all tests share
    the same TestClient IP, prior tests in this module may have consumed
    most of the 10/minute budget on the recommendation endpoint. Reset the
    limiter before exercising the cache path so we actually test caching,
    not rate limiting.
    """
    _override_db(_build_test_db())
    from app.security import limiter

    limiter.reset()

    client = TestClient(app)
    tid = _create_task(client)

    first = client.post(f"/tasks/{tid}/recommendation").json()
    second = client.post(f"/tasks/{tid}/recommendation").json()
    third = client.post(f"/tasks/{tid}/recommendation").json()
    assert "id" in first, f"first call did not return a recommendation: {first}"
    assert first["id"] == second["id"] == third["id"]

    # Now invalidate by adding a sub-task — context hash changes.
    client.post(
        f"/tasks/{tid}/subtasks",
        json={"title": "New step", "canon_reference": "Consistency"},
    )
    fourth = client.post(f"/tasks/{tid}/recommendation").json()
    assert fourth["id"] != first["id"]

    app.dependency_overrides.clear()
