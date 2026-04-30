"""Tests for sub-tasks and obstacles (Phase 2 Day 3).

All tests exercise the mock AIProvider — no live LLM calls.
"""
from collections.abc import Generator

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
        "title": "Parent task",
        "description": "A task with structure",
        "objective": "Make it concrete",
        "standard": "Consistency",
        "status": "up_next",
        "priority": "medium",
        "owner_name": "alex",
        "assigner_name": "jordan",
        "due_at": None,
        "source_confidence": 0.8,
    }
    payload.update(overrides)
    r = client.post("/tasks", json=payload)
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ─── Sub-tasks ──────────────────────────────────────────────────────────


def test_sub_task_crud_lifecycle() -> None:
    _override_db(_build_test_db())
    client = TestClient(app)
    task_id = _create_task(client)

    # Create
    r = client.post(
        f"/tasks/{task_id}/subtasks",
        json={
            "title": "Pin the target outcome",
            "description": "Write one sentence everyone agrees on.",
            "canon_reference": "Anticipation",
        },
    )
    assert r.status_code == 201, r.text
    st_id = r.json()["id"]
    assert r.json()["order"] == 0  # first one starts at 0
    assert r.json()["status"] == "pending"

    # A second sub-task auto-orders after the first.
    r2 = client.post(
        f"/tasks/{task_id}/subtasks",
        json={"title": "Identify smallest next action", "canon_reference": "Ownership"},
    )
    assert r2.status_code == 201
    assert r2.json()["order"] == 1

    # List returns them in order.
    listing = client.get(f"/tasks/{task_id}/subtasks").json()
    assert [s["order"] for s in listing] == [0, 1]

    # Patch status and title.
    r_patch = client.patch(
        f"/subtasks/{st_id}",
        json={"status": "completed", "title": "Outcome pinned"},
    )
    assert r_patch.status_code == 200
    assert r_patch.json()["status"] == "completed"
    assert r_patch.json()["title"] == "Outcome pinned"

    # Delete the other one.
    r_del = client.delete(f"/subtasks/{r2.json()['id']}")
    assert r_del.status_code == 204
    remaining = client.get(f"/tasks/{task_id}/subtasks").json()
    assert len(remaining) == 1

    # 404 on unknown id.
    assert client.patch("/subtasks/9999", json={"title": "nope"}).status_code == 404
    assert client.delete("/subtasks/9999").status_code == 404
    assert client.get("/tasks/9999/subtasks").status_code == 404

    app.dependency_overrides.clear()


def test_generate_sub_tasks_preview_returns_drafts_without_persisting() -> None:
    _override_db(_build_test_db())
    client = TestClient(app)
    task_id = _create_task(client)

    r = client.post(f"/tasks/{task_id}/subtasks/generate")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["task_id"] == task_id
    assert 3 <= len(body["drafts"]) <= 7
    for draft in body["drafts"]:
        assert draft["title"]
        # Each draft references a Standard
        assert draft["canon_reference"]

    # No persistence: the task has zero sub-tasks after generate.
    listing = client.get(f"/tasks/{task_id}/subtasks").json()
    assert listing == []

    app.dependency_overrides.clear()


# ─── Obstacles ─────────────────────────────────────────────────────────


def test_obstacle_crud_lifecycle_and_resolve() -> None:
    _override_db(_build_test_db())
    client = TestClient(app)
    task_id = _create_task(client)

    # Create a manual obstacle with no solutions yet.
    r = client.post(
        f"/tasks/{task_id}/obstacles",
        json={
            "description": "Waiting on vendor credentials",
            "impact": "Blocks onboarding for this residence",
            "identified_by": "alex",
        },
    )
    assert r.status_code == 201, r.text
    ob_id = r.json()["id"]
    assert r.json()["status"] == "active"
    assert r.json()["proposed_solutions"] == []

    # Patch impact text.
    r_patch = client.patch(
        f"/obstacles/{ob_id}",
        json={"impact": "Blocks onboarding AND the Thursday walkthrough"},
    )
    assert r_patch.status_code == 200
    assert "Thursday" in r_patch.json()["impact"]

    # List returns one active obstacle.
    listing = client.get(f"/tasks/{task_id}/obstacles").json()
    assert len(listing) == 1
    assert listing[0]["id"] == ob_id

    # Resolve it.
    r_resolve = client.post(
        f"/obstacles/{ob_id}/resolve",
        json={"resolution_notes": "Vendor sent creds on Monday."},
    )
    assert r_resolve.status_code == 200
    body = r_resolve.json()
    assert body["status"] == "resolved"
    assert body["resolution_notes"].startswith("Vendor")
    assert body["resolved_at"] is not None

    app.dependency_overrides.clear()


def test_analyze_obstacle_populates_proposed_solutions() -> None:
    _override_db(_build_test_db())
    client = TestClient(app)
    task_id = _create_task(client, status="blocked")

    r = client.post(
        f"/tasks/{task_id}/obstacles",
        json={
            "description": "HVAC vendor escalation not returning calls",
            "impact": "Residents raising complaints at the front desk.",
            "identified_by": "alex",
        },
    )
    ob_id = r.json()["id"]

    r_analyze = client.post(f"/obstacles/{ob_id}/analyze")
    assert r_analyze.status_code == 200, r_analyze.text
    body = r_analyze.json()
    solutions = body["proposed_solutions"]
    assert len(solutions) == 3
    for s in solutions:
        assert s["solution"]
        assert s["first_step"]
        assert s["aligned_standard"]
        assert s["source"] == "ai_generated"

    # Re-running analyze replaces the solutions (same count, still 3).
    r_again = client.post(f"/obstacles/{ob_id}/analyze")
    assert r_again.status_code == 200
    assert len(r_again.json()["proposed_solutions"]) == 3

    app.dependency_overrides.clear()


def test_recommendation_context_includes_subtasks_and_obstacles() -> None:
    _override_db(_build_test_db())
    client = TestClient(app)
    task_id = _create_task(client)

    # Add a completed sub-task and an in-progress one.
    client.post(
        f"/tasks/{task_id}/subtasks",
        json={"title": "Step 1", "canon_reference": "Anticipation", "status": "completed"},
    )
    client.post(
        f"/tasks/{task_id}/subtasks",
        json={"title": "Step 2", "canon_reference": "Ownership", "status": "in_progress"},
    )
    # Add an active obstacle.
    client.post(
        f"/tasks/{task_id}/obstacles",
        json={"description": "Open thing", "impact": "slows step 2"},
    )

    rec = client.post(f"/tasks/{task_id}/recommendation")
    assert rec.status_code == 200
    ctx = rec.json()["recommendation_context"]
    assert ctx["subtasks_total"] == 2
    assert ctx["subtasks_completed"] == 1
    assert ctx["active_obstacles"] == 1

    app.dependency_overrides.clear()


def test_resolved_obstacle_resolution_notes_flow_into_prompt_and_bust_cache() -> None:
    """Resolving an obstacle should both:
       - inject its resolution_notes into the next recommendation prompt
       - bust the cache so the recommendation is regenerated, not cached.
    """
    from app.providers import MockAIProvider, RecommendationDraft
    from app.services import (
        create_obstacle_for_task,
        generate_task_recommendation,
        resolve_obstacle_by_id,
    )

    TestingSessionLocal = _build_test_db()
    _override_db(TestingSessionLocal)
    client = TestClient(app)
    task_id = _create_task(client)

    # Capture the system prompt the provider sees on each call.
    captured_prompts: list[str] = []

    class CapturingProvider(MockAIProvider):
        def generate_recommendation(self, *, system_prompt=None, **kwargs):  # type: ignore[override]
            captured_prompts.append(system_prompt or "")
            return RecommendationDraft(
                objective=kwargs.get("objective", ""),
                standard=kwargs.get("standard", ""),
                first_principles_plan="plan",
                viable_options=["a", "b"],
                next_action="do it",
                source_refs=[],
            )

    db = TestingSessionLocal()
    obstacle = create_obstacle_for_task(
        db, task_id, {"description": "Vendor unresponsive", "impact": "delays kickoff"}
    )
    assert obstacle is not None

    provider = CapturingProvider()
    rec1 = generate_task_recommendation(db, task_id, ai_provider=provider)
    assert rec1 is not None
    assert any("Active obstacles" in p for p in captured_prompts)

    # Resolve the obstacle with a distinctive note.
    note = "Vendor confirmed start date — booked Tuesday"
    resolve_obstacle_by_id(db, obstacle.id, note)

    rec2 = generate_task_recommendation(db, task_id, ai_provider=provider)
    assert rec2 is not None
    # Cache must bust: id changes because the input bundle changed.
    assert rec2.id != rec1.id
    # Most recent captured prompt must include the resolution_notes string.
    assert any(note in p for p in captured_prompts[-1:]), (
        "resolution_notes did not flow into the recommendation prompt"
    )
    assert "Recently resolved obstacles" in captured_prompts[-1]

    db.close()
    app.dependency_overrides.clear()


def test_recommendation_api_response_includes_resolved_obstacles_count() -> None:
    """The API consumer must be able to see resolved_obstacles_included in
    recommendation_context. The Pydantic response model used to drop the
    field even though the service layer set it — regression pin.
    """
    from app.services import resolve_obstacle_by_id

    TestingSessionLocal = _build_test_db()
    _override_db(TestingSessionLocal)
    client = TestClient(app)
    task_id = _create_task(client)

    obstacle_resp = client.post(
        f"/tasks/{task_id}/obstacles",
        json={
            "description": "Camera footage missing for week 1",
            "impact": "Cannot identify perpetrator",
        },
    )
    assert obstacle_resp.status_code in (200, 201), obstacle_resp.text
    obstacle_id = obstacle_resp.json()["id"]

    db = TestingSessionLocal()
    resolved = resolve_obstacle_by_id(
        db,
        obstacle_id,
        "Recovered footage from cloud backup via vendor support team",
    )
    assert resolved is not None
    db.close()

    rec = client.post(f"/tasks/{task_id}/recommendation")
    assert rec.status_code == 200, rec.text
    body = rec.json()
    ctx = body["recommendation_context"]
    assert "resolved_obstacles_included" in ctx, (
        f"recommendation_context missing the field; got keys: {list(ctx.keys())}"
    )
    assert ctx["resolved_obstacles_included"] >= 1, (
        f"expected at least 1 resolved obstacle in prompt, got {ctx['resolved_obstacles_included']}"
    )

    app.dependency_overrides.clear()


def test_recommendation_prompt_includes_resolution_citation_instruction() -> None:
    """The prompt body must include both the resolution_notes substring AND
    the explicit citation instruction so the LLM knows to reference recent
    wins by name. Pin both so a future prompt rewrite cannot silently drop
    either piece.
    """
    from app.canon_context import (
        RESOLUTION_CITATION_INSTRUCTION,
        build_standard_system_prompt,
    )

    resolved = [
        {
            "id": 1,
            "description": "Camera footage missing for week 1",
            "impact": "Cannot identify perpetrator",
            "resolution_notes": "Recovered footage from cloud backup via vendor support",
            "resolved_ago_days": 2,
        },
    ]
    prompt = build_standard_system_prompt(
        canon_chunks=[],
        updates=[],
        blocker=None,
        reviews=[],
        history_summary=None,
        subtasks=[],
        active_obstacles=[],
        resolved_obstacles=resolved,
    )

    assert "Recently resolved obstacles" in prompt
    assert "How it was resolved: Recovered footage from cloud backup via vendor support" in prompt
    assert RESOLUTION_CITATION_INSTRUCTION in prompt

    # Resolved-obstacle block must sit in the live-state cluster, BEFORE
    # the supporting structure (reviews, history, sub-tasks). If the
    # builder is reshuffled in the future we want this to fail loudly.
    resolved_idx = prompt.index("Recently resolved obstacles")
    history_idx = prompt.index("Task history summary") if "Task history summary" in prompt else len(prompt)
    review_idx = (
        prompt.index("Recent review sessions") if "Recent review sessions" in prompt else len(prompt)
    )
    earliest_supporting = min(history_idx, review_idx)
    assert resolved_idx < earliest_supporting, (
        "resolved-obstacle block leaked into the supporting-context tail"
    )
