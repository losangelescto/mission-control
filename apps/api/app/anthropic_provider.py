"""Anthropic Claude adapter for AIProvider.

The adapter is deliberately defensive:

- Any exception from the SDK, an HTTP timeout, a malformed JSON response, or a
  missing field in the parsed response results in a graceful fallback to
  MockAIProvider with a breadcrumb added to ``source_refs`` so the caller can
  see that the LLM call did not complete. The API request is never allowed
  to 500 because the LLM is down.
- The SDK is imported lazily so the provider module can be imported cleanly
  in environments that do not have ``anthropic`` installed (e.g. unit tests
  that only exercise the mock path).
- The Anthropic response is parsed as strict JSON. We tolerate a single
  fenced ``json`` code block and strip it before parsing, but we do not try
  to "repair" mangled output — if it cannot be parsed we fall back.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.providers import AIProvider, MockAIProvider, RecommendationDraft, UnblockDraft

logger = logging.getLogger(__name__)

# Strip a ```json ... ``` fence if Claude ignores the "no fences" instruction.
_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


class AnthropicProvider:
    """Real LLM-backed AIProvider that calls Anthropic Claude."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_tokens: int = 1500,
        temperature: float = 0.3,
        fallback: AIProvider | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._fallback = fallback or MockAIProvider()
        self._client = None  # lazily constructed on first use

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import anthropic  # type: ignore[import-not-found]
        except ImportError as exc:  # noqa: BLE001
            raise RuntimeError(
                "anthropic SDK is not installed; set LLM_PROVIDER=mock or install "
                "the anthropic package from requirements.txt"
            ) from exc
        self._client = anthropic.Anthropic(api_key=self._api_key, timeout=30.0)
        return self._client

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
        # Prefer caller-built prompts (services owns context assembly now) —
        # fall back to a minimal pair if a legacy caller still uses the old
        # four-argument form.
        if system_prompt is None or user_message is None:
            from app.canon_context import (
                build_standard_system_prompt,
                build_standard_user_message,
            )

            system_prompt = build_standard_system_prompt(
                canon_chunks=context_chunks,
                updates=[],
                blocker=None,
                reviews=[],
                history_summary=None,
            )
            user_message = build_standard_user_message(
                task={
                    "title": task_description.splitlines()[0] if task_description else "",
                    "description": task_description,
                    "status": "unknown",
                    "priority": "unknown",
                    "owner_name": "unknown",
                    "assigner_name": "unknown",
                    "due_at_display": None,
                },
                objective_seed=objective,
                standard_seed=standard,
            )

        try:
            payload = self._call_llm(system_prompt, user_message)
            return _build_standard_draft(payload, context_chunks, objective, standard)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "anthropic recommendation failed; returning mock fallback",
                extra={
                    "event": "anthropic_recommendation_failed",
                    "context": {"error": str(exc), "model": self._model},
                },
            )
            fallback = self._fallback.generate_recommendation(
                objective=objective,
                standard=standard,
                task_description=task_description,
                context_chunks=context_chunks,
            )
            fallback.source_refs.append(
                {"source": "fallback_due_to_llm_error", "error": str(exc)[:200]}
            )
            return fallback

    def generate_unblock(
        self,
        *,
        system_prompt: str,
        user_message: str,
        context_chunks: list[dict],
    ) -> UnblockDraft:
        try:
            payload = self._call_llm(system_prompt, user_message)
            return _build_unblock_draft(payload, context_chunks)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "anthropic unblock failed; returning mock fallback",
                extra={
                    "event": "anthropic_unblock_failed",
                    "context": {"error": str(exc), "model": self._model},
                },
            )
            fallback = self._fallback.generate_unblock(
                system_prompt=system_prompt,
                user_message=user_message,
                context_chunks=context_chunks,
            )
            fallback.source_refs.append(
                {"source": "fallback_due_to_llm_error", "error": str(exc)[:200]}
            )
            return fallback

    def _call_llm(self, system_prompt: str, user_message: str) -> dict:
        client = self._get_client()
        response = client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        text = _extract_text(response)
        return _parse_json_response(text)


def _extract_text(response: Any) -> str:
    """Pull the concatenated text from an Anthropic messages response."""
    parts: list[str] = []
    for block in getattr(response, "content", []) or []:
        # Anthropic SDK returns ContentBlock objects with .type and .text
        block_type = getattr(block, "type", None)
        if block_type == "text":
            parts.append(getattr(block, "text", "") or "")
    return "".join(parts).strip()


def _parse_json_response(text: str) -> dict:
    if not text:
        raise ValueError("empty response from model")

    # Strip a fenced code block if the model wrapped its output.
    match = _JSON_FENCE_RE.match(text.strip())
    if match:
        text = match.group(1)

    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object, got {type(payload).__name__}")
    return payload


def _refs(context_chunks: list[dict]) -> list[dict]:
    return [
        {
            "source_document_id": chunk.get("source_document_id"),
            "source_filename": chunk.get("source_filename"),
            "chunk_index": chunk.get("chunk_index"),
        }
        for chunk in (context_chunks or [])[:5]
    ]


def _build_standard_draft(
    payload: dict,
    context_chunks: list[dict],
    objective_seed: str,
    standard_seed: str,
) -> RecommendationDraft:
    options_raw = payload.get("viable_options", [])
    if isinstance(options_raw, str):
        options = [options_raw]
    elif isinstance(options_raw, list):
        options = [str(o) for o in options_raw if str(o).strip()]
    else:
        options = []

    # Enforce a sane floor — the API contract requires at least 2 options.
    if len(options) < 2:
        options = options + [
            "Continue with the current approach and reassess at the next checkpoint.",
            "Escalate to the assigner and request a tighter scope.",
        ]
        options = options[:3]

    return RecommendationDraft(
        objective=(payload.get("objective") or objective_seed).strip(),
        standard=(payload.get("standard") or standard_seed).strip(),
        first_principles_plan=(
            payload.get("first_principles_plan") or ""
        ).strip() or "Clarify constraints, pick the lowest-risk path, execute, verify.",
        viable_options=options,
        next_action=(
            payload.get("next_action") or ""
        ).strip() or "Draft the first concrete step and share it with the owner today.",
        source_refs=_refs(context_chunks),
    )


def _build_unblock_draft(payload: dict, context_chunks: list[dict]) -> UnblockDraft:
    alternatives_raw = payload.get("alternatives", [])
    alternatives: list[dict] = []
    if isinstance(alternatives_raw, list):
        for alt in alternatives_raw:
            if not isinstance(alt, dict):
                continue
            alternatives.append(
                {
                    "path": str(alt.get("path", "")).strip() or "Unnamed path",
                    "solves": str(alt.get("solves", "")).strip(),
                    "tradeoff": str(alt.get("tradeoff", "")).strip(),
                    "first_step": str(alt.get("first_step", "")).strip(),
                    "aligned_standard": str(alt.get("aligned_standard", "")).strip(),
                }
            )

    # Enforce the contract of exactly 3 distinct alternatives.
    while len(alternatives) < 3:
        alternatives.append(
            {
                "path": f"Placeholder path {len(alternatives) + 1}",
                "solves": "",
                "tradeoff": "",
                "first_step": "Clarify the blocker with the assigner.",
                "aligned_standard": "Accountability",
            }
        )
    alternatives = alternatives[:3]

    return UnblockDraft(
        blocker_summary=(payload.get("blocker_summary") or "").strip()
        or "Blocker details not provided.",
        root_cause_analysis=(payload.get("root_cause_analysis") or "").strip()
        or "Root cause analysis unavailable; the LLM returned an empty response.",
        alternatives=alternatives,
        recommended_path=(payload.get("recommended_path") or "").strip()
        or f"Path {alternatives[0]['path']}",
        canon_reference=(payload.get("canon_reference") or "").strip()
        or "Canon reference unavailable.",
        source_refs=_refs(context_chunks),
    )
