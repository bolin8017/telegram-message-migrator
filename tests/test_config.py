import pytest


def test_single_user_requires_api_credentials(monkeypatch):
    monkeypatch.setenv("SINGLE_USER_MODE", "true")
    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "abc123")
    from app.config import Settings

    s = Settings()
    assert s.single_user_mode is True
    assert s.telegram_api_id == 12345


def test_multi_user_requires_server_secret(monkeypatch):
    monkeypatch.setenv("SINGLE_USER_MODE", "false")
    monkeypatch.setenv("SERVER_SECRET", "x" * 32)
    from app.config import Settings

    s = Settings()
    assert s.server_secret == "x" * 32


def test_multi_user_api_credentials_optional(monkeypatch):
    monkeypatch.setenv("SINGLE_USER_MODE", "false")
    monkeypatch.setenv("SERVER_SECRET", "x" * 32)
    monkeypatch.delenv("TELEGRAM_API_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_API_HASH", raising=False)
    from app.config import Settings

    # Build without reading .env file so the real .env doesn't interfere
    s = Settings(_env_file=None)
    assert s.telegram_api_id is None


def test_new_settings_fields_exist(monkeypatch):
    monkeypatch.setenv("SINGLE_USER_MODE", "true")
    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "abc123")
    from app.config import Settings

    s = Settings()
    assert s.max_user_contexts == 50
    assert s.max_concurrent_jobs == 10
    assert s.max_messages_per_job == 50000
    assert s.session_expiry_days == 7
    assert s.max_sessions_per_user == 3


def test_validate_single_user_missing_credentials(monkeypatch):
    """validate_settings_for_mode should exit if single-user lacks API creds."""
    monkeypatch.setenv("SINGLE_USER_MODE", "true")
    monkeypatch.delenv("TELEGRAM_API_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_API_HASH", raising=False)
    from app.config import Settings, validate_settings_for_mode

    s = Settings(_env_file=None)
    with pytest.raises(SystemExit):
        validate_settings_for_mode(s)


def test_validate_multi_user_missing_secret(monkeypatch):
    """validate_settings_for_mode should exit if multi-user lacks server_secret."""
    monkeypatch.setenv("SINGLE_USER_MODE", "false")
    monkeypatch.delenv("SERVER_SECRET", raising=False)
    from app.config import Settings, validate_settings_for_mode

    s = Settings(_env_file=None)
    with pytest.raises(SystemExit):
        validate_settings_for_mode(s)


def test_validate_multi_user_short_secret(monkeypatch):
    """validate_settings_for_mode should exit if server_secret < 32 chars."""
    monkeypatch.setenv("SINGLE_USER_MODE", "false")
    monkeypatch.setenv("SERVER_SECRET", "tooshort")
    from app.config import Settings, validate_settings_for_mode

    s = Settings(_env_file=None)
    with pytest.raises(SystemExit):
        validate_settings_for_mode(s)


def test_validate_single_user_passes(monkeypatch):
    """validate_settings_for_mode should not exit for valid single-user config."""
    monkeypatch.setenv("SINGLE_USER_MODE", "true")
    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "abc123")
    from app.config import Settings, validate_settings_for_mode

    s = Settings(_env_file=None)
    # Should not raise
    validate_settings_for_mode(s)


def test_validate_multi_user_passes(monkeypatch):
    """validate_settings_for_mode should not exit for valid multi-user config."""
    monkeypatch.setenv("SINGLE_USER_MODE", "false")
    monkeypatch.setenv("SERVER_SECRET", "x" * 32)
    from app.config import Settings, validate_settings_for_mode

    s = Settings(_env_file=None)
    # Should not raise
    validate_settings_for_mode(s)


def test_relay_settings_defaults():
    from app.config import get_settings

    s = get_settings()
    assert s.relay_forward_base_delay == 4.0
    assert s.live_relay_cleanup_threshold == 10
    assert s.relay_group_title == "TMM Relay"
