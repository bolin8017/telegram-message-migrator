"""Tests for CORS_ORIGINS environment variable parsing."""

from app.main import _parse_cors_origins


def test_default_when_env_unset():
    """Unset env → defaults to localhost dev origins."""
    assert _parse_cors_origins(None) == [
        "http://localhost:5173",
        "http://localhost:8000",
    ]


def test_single_origin():
    """One origin parses to a single-element list."""
    assert _parse_cors_origins("https://tgmigrate.com") == [
        "https://tgmigrate.com",
    ]


def test_comma_separated_origins():
    """Comma-separated origins parse into a list in order."""
    assert _parse_cors_origins("https://a.example,https://b.example") == [
        "https://a.example",
        "https://b.example",
    ]


def test_whitespace_is_trimmed():
    """Whitespace around origins is stripped."""
    assert _parse_cors_origins("  https://a.example , https://b.example  ") == [
        "https://a.example",
        "https://b.example",
    ]


def test_empty_entries_are_dropped():
    """Empty entries (from trailing commas etc.) are dropped."""
    assert _parse_cors_origins("https://a.example,,https://b.example,") == [
        "https://a.example",
        "https://b.example",
    ]


def test_empty_string_returns_empty_list():
    """An explicitly empty string yields an empty list (locks the app down)."""
    assert _parse_cors_origins("") == []
