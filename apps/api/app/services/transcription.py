"""Provider-based transcription service.

Two providers:
  - MockTranscriptionProvider: deterministic, no network, used for tests
    and local dev. Selected via TRANSCRIPTION_PROVIDER=mock (default).
  - WhisperTranscriptionProvider: OpenAI Whisper API. Selected via
    TRANSCRIPTION_PROVIDER=whisper. Lazy-imports the openai package so
    the API can boot without it installed.

For files larger than the Whisper API single-call limit, the provider
splits the audio into ~10-minute chunks via pydub, transcribes each
chunk independently, and stitches the segments back together with
chunk-relative timestamps shifted into absolute time.
"""
from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from app.config import get_settings
from app.services.audio_utils import (
    WHISPER_BYTE_LIMIT,
    extract_audio_from_video,
    is_video_file,
)

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_MINUTES = 10


@dataclass
class TranscriptionSegment:
    start_time: float
    end_time: float
    text: str
    speaker: str = "Speaker 1"


@dataclass
class TranscriptionResult:
    full_text: str
    segments: list[TranscriptionSegment]
    duration_seconds: float
    confidence: float

    def segments_as_dicts(self) -> list[dict]:
        return [asdict(s) for s in self.segments]


class TranscriptionError(RuntimeError):
    """Transcription failed; caller should mark the source as failed/partial."""


class TranscriptionProvider(Protocol):
    def transcribe(self, file_path: Path) -> TranscriptionResult: ...


# ─── Mock ────────────────────────────────────────────────────────────


@dataclass
class MockTranscriptionProvider:
    """Returns a plausible 3-segment transcription with two-speaker dialogue.

    Speakers alternate Speaker 1 / Speaker 2 to exercise the diarization
    rendering path even when no real diarization is available.
    """

    duration_seconds: float = 180.0
    confidence: float = 0.85

    def transcribe(self, file_path: Path) -> TranscriptionResult:
        del file_path  # only the file's existence matters for the mock
        segments = [
            TranscriptionSegment(
                start_time=0.0,
                end_time=60.0,
                text="Thanks for joining the call. Let's walk through the open items on this property.",
                speaker="Speaker 1",
            ),
            TranscriptionSegment(
                start_time=60.0,
                end_time=120.0,
                text="The roof inspection report came back. There's a section over the east wing that needs attention before the next storm season.",
                speaker="Speaker 2",
            ),
            TranscriptionSegment(
                start_time=120.0,
                end_time=self.duration_seconds,
                text="Action item: pull a quote from the roofing contractor by end of week and circle back on the invoice cadence.",
                speaker="Speaker 1",
            ),
        ]
        full_text = "\n".join(f"[{seg.speaker}] {seg.text}" for seg in segments)
        return TranscriptionResult(
            full_text=full_text,
            segments=segments,
            duration_seconds=self.duration_seconds,
            confidence=self.confidence,
        )


# ─── Whisper (OpenAI) ────────────────────────────────────────────────


@dataclass
class WhisperTranscriptionProvider:
    api_key: str
    model: str = "whisper-1"
    chunk_minutes: int = DEFAULT_CHUNK_MINUTES

    def transcribe(self, file_path: Path) -> TranscriptionResult:
        # Demux video before sending to Whisper (Whisper accepts audio only).
        if is_video_file(file_path):
            file_path = extract_audio_from_video(file_path)

        size = file_path.stat().st_size
        if size <= WHISPER_BYTE_LIMIT:
            return self._transcribe_single(file_path)
        return self._transcribe_chunked(file_path)

    def _client(self):
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as exc:
            raise TranscriptionError(
                "openai package is required for the whisper transcription provider"
            ) from exc
        return OpenAI(api_key=self.api_key)

    def _transcribe_single(self, file_path: Path) -> TranscriptionResult:
        client = self._client()
        try:
            with file_path.open("rb") as fh:
                response = client.audio.transcriptions.create(
                    file=fh,
                    model=self.model,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )
        except Exception as exc:
            raise TranscriptionError(f"whisper API call failed: {exc}") from exc
        return _result_from_whisper_response(response)

    def _transcribe_chunked(self, file_path: Path) -> TranscriptionResult:
        try:
            from pydub import AudioSegment  # type: ignore
        except ImportError as exc:
            raise TranscriptionError(
                "pydub is required to split audio for the whisper provider"
            ) from exc

        audio = AudioSegment.from_file(file_path)
        total_ms = len(audio)
        chunk_ms = self.chunk_minutes * 60 * 1000
        num_chunks = math.ceil(total_ms / chunk_ms)
        logger.info(
            "whisper chunked transcription",
            extra={
                "event": "whisper_chunked",
                "context": {"chunks": num_chunks, "duration_ms": total_ms},
            },
        )

        all_segments: list[TranscriptionSegment] = []
        full_text_parts: list[str] = []

        for i in range(num_chunks):
            start_ms = i * chunk_ms
            end_ms = min(start_ms + chunk_ms, total_ms)
            chunk = audio[start_ms:end_ms]
            chunk_path = file_path.with_suffix(f".chunk{i}.mp3")
            chunk.export(chunk_path, format="mp3")
            try:
                partial = self._transcribe_single(chunk_path)
            finally:
                chunk_path.unlink(missing_ok=True)

            offset = start_ms / 1000.0
            for seg in partial.segments:
                all_segments.append(
                    TranscriptionSegment(
                        start_time=seg.start_time + offset,
                        end_time=seg.end_time + offset,
                        text=seg.text,
                        speaker=seg.speaker,
                    )
                )
            full_text_parts.append(partial.full_text)

        return TranscriptionResult(
            full_text="\n".join(full_text_parts).strip(),
            segments=all_segments,
            duration_seconds=total_ms / 1000.0,
            confidence=0.0,  # Whisper does not return a single confidence score
        )


def _result_from_whisper_response(response) -> TranscriptionResult:
    """Translate OpenAI verbose_json into TranscriptionResult.

    Whisper does not provide speaker diarization out of the box; we label
    every segment "Speaker 1" so the schema stays consistent.
    """
    text = getattr(response, "text", "") or ""
    duration = float(getattr(response, "duration", 0.0) or 0.0)
    raw_segments = getattr(response, "segments", []) or []
    segments: list[TranscriptionSegment] = []
    for s in raw_segments:
        start = float(getattr(s, "start", 0.0) or 0.0)
        end = float(getattr(s, "end", start) or start)
        seg_text = (getattr(s, "text", "") or "").strip()
        segments.append(
            TranscriptionSegment(
                start_time=start,
                end_time=end,
                text=seg_text,
                speaker="Speaker 1",
            )
        )
    return TranscriptionResult(
        full_text=text.strip(),
        segments=segments,
        duration_seconds=duration,
        confidence=0.0,
    )


# ─── Factory ─────────────────────────────────────────────────────────


def get_transcription_provider() -> TranscriptionProvider:
    settings = get_settings()
    name = (settings.transcription_provider or "mock").strip().lower()
    if name == "whisper":
        if not settings.whisper_api_key:
            logger.warning(
                "whisper provider requested without WHISPER_API_KEY; falling back to mock"
            )
            return MockTranscriptionProvider()
        return WhisperTranscriptionProvider(
            api_key=settings.whisper_api_key,
            model=settings.whisper_model,
        )
    return MockTranscriptionProvider()


__all__ = [
    "MockTranscriptionProvider",
    "TranscriptionError",
    "TranscriptionProvider",
    "TranscriptionResult",
    "TranscriptionSegment",
    "WhisperTranscriptionProvider",
    "get_transcription_provider",
]
