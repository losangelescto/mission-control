from pathlib import Path
from unittest.mock import patch

import pytest

from app.config import get_settings
from app.services import transcription
from app.services.audio_utils import file_kind, is_audio_file, is_video_file
from app.services.transcription import (
    MockTranscriptionProvider,
    TranscriptionError,
    WhisperTranscriptionProvider,
    _result_from_whisper_response,
    get_transcription_provider,
)


def test_file_kind_classification(tmp_path: Path) -> None:
    assert file_kind(tmp_path / "doc.pdf") == "pdf"
    assert file_kind(tmp_path / "call.mp3") == "audio"
    assert file_kind(tmp_path / "call.WAV") == "audio"
    assert file_kind(tmp_path / "meeting.mp4") == "video"
    assert file_kind(tmp_path / "notes.txt") == "text"
    assert file_kind(tmp_path / "notes.docx") == "text"
    assert file_kind(tmp_path / "image.png") == "unknown"

    assert is_audio_file(tmp_path / "track.flac") is True
    assert is_audio_file(tmp_path / "movie.mp4") is False
    assert is_video_file(tmp_path / "movie.webm") is True


def test_mock_transcription_returns_segments(tmp_path: Path) -> None:
    provider = MockTranscriptionProvider()
    result = provider.transcribe(tmp_path / "anything.mp3")
    assert result.duration_seconds > 0
    assert len(result.segments) == 3
    speakers = {seg.speaker for seg in result.segments}
    assert speakers == {"Speaker 1", "Speaker 2"}
    assert all(seg.text for seg in result.segments)
    assert "[Speaker 1]" in result.full_text


def test_get_transcription_provider_defaults_to_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "transcription_provider", "mock")
    assert isinstance(get_transcription_provider(), MockTranscriptionProvider)


def test_get_transcription_provider_falls_back_when_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "transcription_provider", "whisper")
    monkeypatch.setattr(settings, "whisper_api_key", "")
    # Without an API key, the factory must not return a Whisper provider.
    assert isinstance(get_transcription_provider(), MockTranscriptionProvider)


def test_get_transcription_provider_returns_whisper(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "transcription_provider", "whisper")
    monkeypatch.setattr(settings, "whisper_api_key", "test-key")
    provider = get_transcription_provider()
    assert isinstance(provider, WhisperTranscriptionProvider)
    assert provider.api_key == "test-key"


def test_result_from_whisper_response_normalizes_segments() -> None:
    class _Segment:
        def __init__(self, start: float, end: float, text: str) -> None:
            self.start = start
            self.end = end
            self.text = text

    class _Response:
        text = "Full text body"
        duration = 42.5
        segments = [_Segment(0.0, 5.0, "Hello"), _Segment(5.0, 10.0, "World")]

    result = _result_from_whisper_response(_Response())
    assert result.full_text == "Full text body"
    assert result.duration_seconds == 42.5
    assert len(result.segments) == 2
    assert result.segments[0].speaker == "Speaker 1"
    assert result.segments[0].text == "Hello"


def test_whisper_provider_raises_when_openai_missing(tmp_path: Path) -> None:
    audio = tmp_path / "track.mp3"
    audio.write_bytes(b"\x00" * 16)
    provider = WhisperTranscriptionProvider(api_key="key")

    with patch.object(transcription, "is_video_file", return_value=False):
        with patch.dict("sys.modules", {"openai": None}):
            # Force the lazy import to fail by clearing it from sys.modules
            # and patching openai to None so importing raises.
            with pytest.raises(TranscriptionError):
                provider._client()
