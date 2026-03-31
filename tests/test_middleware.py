from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

# Import for patching
from app.middleware import create_session_cookie, hash_token, validate_session_binding


def test_create_session_cookie_returns_token():
    token = create_session_cookie()
    assert len(token) >= 32
    assert isinstance(token, str)


def test_create_session_cookie_unique():
    t1 = create_session_cookie()
    t2 = create_session_cookie()
    assert t1 != t2


def test_hash_token_deterministic():
    assert hash_token("test") == hash_token("test")


def test_hash_token_different_inputs():
    assert hash_token("a") != hash_token("b")


@pytest.mark.asyncio
async def test_require_user_no_cookie_raises_401():
    from app.middleware import require_user

    request = MagicMock()
    request.cookies = {}
    with pytest.raises(HTTPException) as exc_info:
        await require_user(request)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_require_user_valid_cookie_returns_context():
    from app.middleware import require_user
    from app.user_context import UserContext, register_context

    ctx = UserContext(user_id=123, session_token="valid_tok")
    register_context(ctx)
    request = MagicMock()
    request.cookies = {"session_id": "valid_tok"}
    result = await require_user(request)
    assert result is ctx


@pytest.mark.asyncio
async def test_require_user_unknown_cookie_raises_401():
    from app.middleware import require_user

    request = MagicMock()
    request.cookies = {"session_id": "unknown_tok"}
    # Mock _rebuild_user_context to return None (no DB record)
    with patch("app.middleware._rebuild_user_context", new_callable=AsyncMock, return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            await require_user(request)
        assert exc_info.value.status_code == 401


def test_session_binding_ua_changed_fails():
    assert validate_session_binding("old_ua", "new_ua") is False


def test_session_binding_ua_same_passes():
    assert validate_session_binding("same", "same") is True


async def test_require_user_session_binding_ua_changed_raises_401():
    """When UA differs from stored value, require_user should raise 401."""
    from app.middleware import hash_user_agent, require_user
    from app.user_context import UserContext, register_context

    ctx = UserContext(
        user_id=999,
        session_token="binding_tok",
        user_agent_hash=hash_user_agent("OriginalBrowser/1.0"),
        ip_prefix="192.168.1",
    )
    register_context(ctx)

    request = MagicMock()
    request.cookies = {"session_id": "binding_tok"}
    request.headers = {"user-agent": "CompletelyDifferentBrowser/2.0"}
    request.client = MagicMock()
    request.client.host = "192.168.1.100"  # same IP — only UA changed

    with pytest.raises(HTTPException) as exc_info:
        await require_user(request)
    assert exc_info.value.status_code == 401
    assert "Session binding changed" in exc_info.value.detail


def test_extract_ip_prefix_ipv4():
    """IPv4 prefix should be first 3 octets."""
    from app.middleware import extract_ip_prefix

    assert extract_ip_prefix("192.168.1.100") == "192.168.1"


def test_extract_ip_prefix_ipv6():
    """IPv6 prefix should be first 4 groups."""
    from app.middleware import extract_ip_prefix

    assert extract_ip_prefix("2001:0db8:85a3:0000:0000:8a2e:0370:7334") == "2001:0db8:85a3:0000"
