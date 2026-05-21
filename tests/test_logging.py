"""Tests for the JSON log formatter."""

import json
import logging

from app.main import _JsonFormatter


def test_json_formatter_emits_required_fields():
    formatter = _JsonFormatter()
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname="x.py",
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    payload = json.loads(formatter.format(record))
    assert payload["level"] == "INFO"
    assert payload["logger"] == "app.test"
    assert payload["message"] == "hello world"
    assert "ts" in payload


def test_json_formatter_includes_exc_info_when_present():
    formatter = _JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        exc_info = sys.exc_info()
    record = logging.LogRecord(
        name="app.test",
        level=logging.ERROR,
        pathname="x.py",
        lineno=1,
        msg="oops",
        args=(),
        exc_info=exc_info,
    )
    payload = json.loads(formatter.format(record))
    assert payload["level"] == "ERROR"
    assert "ValueError: boom" in payload["exc_info"]


def test_json_formatter_no_exc_info_field_when_absent():
    formatter = _JsonFormatter()
    record = logging.LogRecord(
        name="x", level=logging.DEBUG, pathname="x.py", lineno=1, msg="m", args=(), exc_info=None
    )
    payload = json.loads(formatter.format(record))
    assert "exc_info" not in payload
