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
