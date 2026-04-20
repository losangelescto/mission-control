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


class AIProvider(Protocol):
    def generate_recommendation(
        self,
        *,
        objective: str,
        standard: str,
        task_description: str,
        context_chunks: list[dict],
    ) -> RecommendationDraft:
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
    ) -> RecommendationDraft:
        refs = [
            {
                "source_document_id": chunk["source_document_id"],
                "source_filename": chunk["source_filename"],
                "chunk_index": chunk["chunk_index"],
            }
            for chunk in context_chunks[:5]
        ]
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
