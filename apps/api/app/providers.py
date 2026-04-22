import hashlib
from dataclasses import dataclass
from typing import Protocol


class EmbeddingsAdapter(Protocol):
    def embed_text(self, text: str) -> list[float]:
        ...


@dataclass
class RecommendationDraft:
    objective: str
    standard: str
    first_principles_plan: str
    viable_options: list[str]
    next_action: str
    source_refs: list[dict]


@dataclass
class UnblockDraft:
    """Structured output when the recommendation engine is in unblock mode.

    Distinct shape from RecommendationDraft — a blocked task gets a
    root-cause analysis plus three first-principles alternatives, not the
    standard objective/plan/options/next-action skeleton. Callers that need
    to persist both modes into the same row should synthesise the standard
    fields from the recommended alternative (see services layer).
    """

    blocker_summary: str
    root_cause_analysis: str
    alternatives: list[dict]
    recommended_path: str
    canon_reference: str
    source_refs: list[dict]


class AIProvider(Protocol):
    def generate_recommendation(
        self,
        *,
        objective: str,
        standard: str,
        task_description: str,
        context_chunks: list[dict],
        system_prompt: str | None = None,
        user_message: str | None = None,
    ) -> RecommendationDraft:
        ...

    def generate_unblock(
        self,
        *,
        system_prompt: str,
        user_message: str,
        context_chunks: list[dict],
    ) -> UnblockDraft:
        ...


class MockEmbeddingsAdapter:
    dimension = 1536

    def embed_text(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        for i in range(self.dimension):
            byte = digest[i % len(digest)]
            vec[i] = (byte / 255.0) - 0.5
        return vec


class MockAIProvider:
    def generate_recommendation(
        self,
        *,
        objective: str,
        standard: str,
        task_description: str,
        context_chunks: list[dict],
        system_prompt: str | None = None,
        user_message: str | None = None,
    ) -> RecommendationDraft:
        refs = _refs_from_chunks(context_chunks)
        return RecommendationDraft(
            objective=objective,
            standard=standard,
            first_principles_plan=(
                "1) Clarify constraints from canon and recent sources. "
                "2) Pick lowest-risk path. 3) Execute and verify outcomes."
            ),
            viable_options=[
                "Option A: conservative path aligned to active canon",
                "Option B: faster path using recent source history",
                "Option C: hybrid staged rollout with checkpoints",
            ],
            next_action=f"Draft implementation checklist for: {task_description[:80]}",
            source_refs=refs,
        )

    def generate_unblock(
        self,
        *,
        system_prompt: str,
        user_message: str,
        context_chunks: list[dict],
    ) -> UnblockDraft:
        refs = _refs_from_chunks(context_chunks)
        alternatives = [
            {
                "path": "Conservative rollback",
                "solves": "Removes the immediate blocker by reverting to the last known-good state.",
                "tradeoff": "Delays forward progress until the root cause is understood.",
                "first_step": "Snapshot current state, then restore the prior configuration.",
                "aligned_standard": "Consistency",
            },
            {
                "path": "Targeted fix",
                "solves": "Addresses the specific root cause without rolling back surrounding work.",
                "tradeoff": "Requires deeper diagnosis time before action.",
                "first_step": "Run diagnostics to confirm the root cause before changing production state.",
                "aligned_standard": "Accountability",
            },
            {
                "path": "Escalate and reassign",
                "solves": "Brings in the right owner or specialist to unblock faster than trial-and-error.",
                "tradeoff": "Uses political capital and hands off context that must be rebuilt.",
                "first_step": "Draft a one-page handoff note and send it to the assigner today.",
                "aligned_standard": "Ownership",
            },
        ]
        return UnblockDraft(
            blocker_summary="Placeholder blocker summary from mock provider.",
            root_cause_analysis=(
                "Mock provider: treat this as a stand-in. The real provider "
                "will diagnose based on the update history and the canon."
            ),
            alternatives=alternatives,
            recommended_path="Path Targeted fix because it addresses the cause, not the symptom.",
            canon_reference="Canon: pick the lowest-risk path that still closes the loop.",
            source_refs=refs,
        )


def _refs_from_chunks(context_chunks: list[dict]) -> list[dict]:
    return [
        {
            "source_document_id": chunk.get("source_document_id"),
            "source_filename": chunk.get("source_filename"),
            "chunk_index": chunk.get("chunk_index"),
        }
        for chunk in (context_chunks or [])[:5]
    ]


def get_ai_provider() -> AIProvider:
    """Return the AIProvider configured by LLM_PROVIDER.

    Defaults to the deterministic mock so local dev and tests never need a
    real API key. Unknown provider names fall back to the mock and log a
    warning on the next recommendation call.
    """
    # Imports here rather than at module top so the mock path has zero
    # runtime dependency on the anthropic SDK or pydantic-settings costs.
    import logging

    from app.config import get_settings

    settings = get_settings()
    provider_name = (settings.llm_provider or "mock").strip().lower()

    if provider_name == "mock":
        return MockAIProvider()

    if provider_name == "anthropic":
        if not settings.llm_api_key:
            logging.getLogger(__name__).warning(
                "LLM_PROVIDER=anthropic but LLM_API_KEY is empty; using mock provider",
                extra={"event": "llm_config_missing_key"},
            )
            return MockAIProvider()
        from app.anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
        )

    logging.getLogger(__name__).warning(
        "unknown LLM_PROVIDER %r; falling back to mock provider",
        provider_name,
        extra={"event": "llm_config_unknown_provider"},
    )
    return MockAIProvider()
