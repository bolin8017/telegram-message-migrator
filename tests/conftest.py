"""Shared fixtures and constants for the test suite."""

import pytest

import app.user_context

# ── Test constants ────────────────────────────────────────────────────

TEST_API_ID = "12345"
TEST_API_HASH = "abc123"
TEST_SERVER_SECRET = "a" * 32


# ── Shared autouse fixtures ──────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_settings_cache(monkeypatch):
    """Clear the module-level _settings cache before each test.

    This ensures each test can configure its own environment variables
    without leaking state from a previous test's Settings instantiation.
    """
    monkeypatch.setattr("app.config._settings", None)


@pytest.fixture(autouse=True)
def clear_user_context_registry():
    """Ensure the user context registry is clean between tests.

    Clears both the token->context map and the user->session-count map
    before and after each test.
    """
    app.user_context._contexts.clear()
    app.user_context._user_sessions.clear()
    yield
    app.user_context._contexts.clear()
    app.user_context._user_sessions.clear()
