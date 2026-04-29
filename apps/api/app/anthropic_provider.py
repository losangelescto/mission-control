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

from app.providers import (
    AIProvider,
    CanonChangeAnalysis,
    ExtractedCandidate,
    MockAIProvider,
    RecommendationDraft,
    SubTaskDraftItem,
    UnblockDraft,
)

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

    def generate_subtasks(
        self,
        *,
        system_prompt: str,
        user_message: str,
    ) -> list[SubTaskDraftItem]:
        try:
            payload = self._call_llm(system_prompt, user_message)
            return _build_subtask_drafts(payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "anthropic subtask generation failed; returning mock fallback",
                extra={
                    "event": "anthropic_subtasks_failed",
                    "context": {"error": str(exc), "model": self._model},
                },
            )
            return self._fallback.generate_subtasks(
                system_prompt=system_prompt,
                user_message=user_message,
            )

    def extract_candidates(
        self,
        *,
        system_prompt: str,
        user_message: str,
    ) -> list[ExtractedCandidate]:
        try:
            payload = self._call_llm(system_prompt, user_message)
            return _build_extracted_candidates(payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "anthropic candidate extraction failed; returning mock fallback",
                extra={
                    "event": "anthropic_extract_candidates_failed",
                    "context": {"error": str(exc), "model": self._model},
                },
            )
            return self._fallback.extract_candidates(
                system_prompt=system_prompt,
                user_message=user_message,
            )

    def analyze_canon_change(
        self,
        *,
        system_prompt: str,
        user_message: str,
    ) -> CanonChangeAnalysis:
        try:
            payload = self._call_llm(system_prompt, user_message)
            return _build_canon_change_analysis(payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "anthropic canon-change analysis failed; returning mock fallback",
                extra={
                    "event": "anthropic_canon_change_failed",
                    "context": {"error": str(exc), "model": self._model},
                },
            )
            return self._fallback.analyze_canon_change(
                system_prompt=system_prompt,
                user_message=user_message,
            )

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


def _build_subtask_drafts(payload: dict) -> list[SubTaskDraftItem]:
    # Accept either {subtasks: [...]} or a raw list at the root.
    raw = payload.get("subtasks") if isinstance(payload, dict) else None
    if raw is None and isinstance(payload, list):
        raw = payload
    if not isinstance(raw, list):
        raw = []

    drafts: list[SubTaskDraftItem] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        drafts.append(
            SubTaskDraftItem(
                title=title,
                description=str(item.get("description", "")).strip(),
                canon_reference=str(item.get("canon_reference", "")).strip()
                or str(item.get("aligned_standard", "")).strip(),
            )
        )

    # Floor: the contract says 3-7 steps. Pad from the mock if the LLM
    # undershoots so the UI always has something to render.
    if len(drafts) < 3:
        for extra in MockAIProvider().generate_subtasks(system_prompt="", user_message=""):
            if len(drafts) >= 3:
                break
            drafts.append(extra)
    return drafts[:7]


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


_EXTRACTION_KINDS = {"action_item", "decision", "discussion"}
_PRIORITY_LEVELS = {"low", "medium", "high"}


def _build_extracted_candidates(payload: dict) -> list[ExtractedCandidate]:
    raw = payload.get("candidates") if isinstance(payload, dict) else None
    if raw is None and isinstance(payload, list):
        raw = payload
    if not isinstance(raw, list):
        return []

    candidates: list[ExtractedCandidate] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        kind = str(item.get("extraction_kind", "")).strip().lower()
        if kind not in _EXTRACTION_KINDS:
            kind = "discussion"
        priority = str(item.get("suggested_priority", "")).strip().lower()
        if priority not in _PRIORITY_LEVELS:
            priority = "medium"
        try:
            confidence = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        candidates.append(
            ExtractedCandidate(
                title=title[:255],
                description=str(item.get("description", "")).strip(),
                suggested_owner=(
                    str(item.get("suggested_owner")).strip()
                    if item.get("suggested_owner")
                    else None
                ),
                suggested_priority=priority,
                suggested_due_date_iso=(
                    str(item.get("suggested_due_date")).strip()
                    if item.get("suggested_due_date")
                    else None
                ),
                source_reference=str(item.get("source_reference", "")).strip(),
                source_timestamp=(
                    str(item.get("source_timestamp")).strip()
                    if item.get("source_timestamp")
                    else None
                ),
                confidence=confidence,
                canon_alignment=str(item.get("canon_alignment", "")).strip(),
                extraction_kind=kind,
            )
        )
    return candidates


def _build_canon_change_analysis(payload: dict) -> CanonChangeAnalysis:
    titles_raw = payload.get("affected_task_titles", [])
    if isinstance(titles_raw, list):
        titles = [str(t).strip() for t in titles_raw if str(t).strip()]
    else:
        titles = []
    return CanonChangeAnalysis(
        change_summary=(payload.get("change_summary") or "").strip()
        or "Change summary unavailable from the LLM response.",
        impact_analysis=(payload.get("impact_analysis") or "").strip()
        or "No impact analysis was returned.",
        affected_task_titles=titles,
    )
