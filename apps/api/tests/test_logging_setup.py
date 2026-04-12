import json
import logging

from app.logging_setup import JsonFormatter


def test_json_formatter_includes_event_and_context() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="app.services",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="message",
        args=(),
        exc_info=None,
    )
    record.event = "demo_event"  # type: ignore[attr-defined]
    record.context = {"key": "value"}  # type: ignore[attr-defined]

    payload = json.loads(formatter.format(record))
    assert payload["message"] == "message"
    assert payload["event"] == "demo_event"
    assert payload["context"] == {"key": "value"}
