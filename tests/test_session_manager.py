from unittest.mock import MagicMock, patch

from app.telegram_client import SessionManager


def test_init_stores_credentials():
    sm = SessionManager(api_id=99999, api_hash="test_hash")
    assert sm._api_id == 99999
    assert sm._api_hash == "test_hash"


def test_init_with_session_dir():
    from pathlib import Path

    sm = SessionManager(api_id=1, api_hash="h", session_dir=Path("/tmp/test_sessions"))
    assert sm._session_dir == Path("/tmp/test_sessions")


def test_create_client_uses_injected_credentials():
    sm = SessionManager(api_id=99999, api_hash="test_hash")
    with patch("app.telegram_client.TelegramClient") as mock_tc:
        mock_tc.return_value = MagicMock()
        sm.get_client("account_a")
        call_args = mock_tc.call_args
        assert call_args[0][1] == 99999  # api_id
        assert call_args[0][2] == "test_hash"  # api_hash


def test_string_session_when_no_session_dir():
    """Without session_dir, should use StringSession."""
    sm = SessionManager(api_id=99999, api_hash="test_hash")  # no session_dir
    with patch("app.telegram_client.TelegramClient") as mock_tc:
        mock_tc.return_value = MagicMock()
        sm.get_client("account_a")
        call_args = mock_tc.call_args
        from telethon.sessions import StringSession

        assert isinstance(call_args[0][0], StringSession)


def test_string_session_with_existing_data():
    """When session_string is provided, use StringSession with that data."""
    sm = SessionManager(api_id=99999, api_hash="test_hash")
    mock_ss_instance = MagicMock()
    with (
        patch("app.telegram_client.TelegramClient") as mock_tc,
        patch("telethon.sessions.StringSession", return_value=mock_ss_instance) as mock_ss_cls,
    ):
        mock_tc.return_value = MagicMock()
        # Use a new client name to avoid cache
        sm.get_client("account_b", session_string="1BVtsOKtest")
        # StringSession was called with the session_string
        mock_ss_cls.assert_called_once_with("1BVtsOKtest")
        # The mock StringSession instance was passed to TelegramClient
        call_args = mock_tc.call_args
        assert call_args[0][0] is mock_ss_instance


def test_client_caching():
    """Second call returns cached client."""
    sm = SessionManager(api_id=1, api_hash="h")
    with patch("app.telegram_client.TelegramClient") as mock_tc:
        mock_tc.return_value = MagicMock()
        c1 = sm.get_client("account_a")
        c2 = sm.get_client("account_a")
        assert c1 is c2
        assert mock_tc.call_count == 1  # only created once


def test_no_module_singleton():
    """The module-level singleton should be removed."""
    import app.telegram_client as mod

    assert not hasattr(mod, "session_manager"), "Module-level singleton should be removed"
