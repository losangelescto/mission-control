"""File-type detection and ffmpeg audio extraction.

Kept dependency-free at import time. The ffmpeg binary is only required
when transcribing video (the mock provider and audio-only files do not
shell out).
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = frozenset({".mp3", ".wav", ".m4a", ".ogg", ".flac"})
VIDEO_EXTENSIONS = frozenset({".mp4", ".webm", ".mov"})
TEXT_EXTENSIONS = frozenset({".txt", ".docx"})
PDF_EXTENSIONS = frozenset({".pdf"})

WHISPER_BYTE_LIMIT = 25 * 1024 * 1024  # OpenAI Whisper API single-call limit
DEFAULT_VIDEO_AUDIO_FORMAT = "mp3"


class FfmpegMissingError(RuntimeError):
    """ffmpeg binary was not found on PATH."""


def file_kind(path: Path) -> str:
    """Return one of: 'pdf' | 'audio' | 'video' | 'text' | 'unknown'."""
    suffix = path.suffix.lower()
    if suffix in PDF_EXTENSIONS:
        return "pdf"
    if suffix in AUDIO_EXTENSIONS:
        return "audio"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    if suffix in TEXT_EXTENSIONS:
        return "text"
    return "unknown"


def is_audio_file(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTENSIONS


def is_video_file(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS


def require_ffmpeg() -> str:
    binary = shutil.which("ffmpeg")
    if binary is None:
        raise FfmpegMissingError(
            "ffmpeg is required for video transcription but was not found on PATH"
        )
    return binary


def extract_audio_from_video(video_path: Path, *, output_format: str = DEFAULT_VIDEO_AUDIO_FORMAT) -> Path:
    """Demux a video file's audio track to a sibling file. Returns the new path."""
    binary = require_ffmpeg()
    output_path = video_path.with_suffix(f".extracted.{output_format}")
    cmd = [
        binary,
        "-y",
        "-i", str(video_path),
        "-vn",
        "-acodec", "libmp3lame" if output_format == "mp3" else "copy",
        str(output_path),
    ]
    logger.info("extracting audio from video", extra={"event": "ffmpeg_extract_audio", "context": {"input": str(video_path)}})
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()[:500]}")
    return output_path
