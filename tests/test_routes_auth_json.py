"""Tests for the JSON auth routes (app/routes/auth.py).

Uses a minimal FastAPI app with just the auth router to avoid broken imports
in app/main.py (which still references the removed session_manager singleton).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from telethon import errors

from app.routes.auth import PendingAuth, _pending_auths, limiter, router
from app.telegram_client import SessionManager

from .conftest import TEST_API_HASH, TEST_API_ID

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clear_pending_auths():
    """Ensure pending auths are empty before and after each test."""
    _pending_auths.clear()
    yield
    _pending_auths.clear()


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset slowapi in-memory rate limit counters between tests."""
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _make_app(single_user_mode: bool = True) -> FastAPI:
    """Create a minimal FastAPI app with just the auth router."""
    app = FastAPI()
    app.include_router(router)
    if single_user_mode:
        app.state.session_manager = MagicMock(spec=SessionManager)
    return app


def _make_client(app: FastAPI) -> AsyncClient:
    """Create an httpx async test client."""
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    )


# ── GET /api/auth/status ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_auth_status_returns_json(monkeypatch):
    """GET /api/auth/status returns JSON with account_a and account_b fields."""
    monkeypatch.setenv("SINGLE_USER_MODE", "true")
    monkeypatch.setenv("TELEGRAM_API_ID", TEST_API_ID)
    monkeypatch.setenv("TELEGRAM_API_HASH", TEST_API_HASH)

    app = _make_app(single_user_mode=True)
    app.state.session_manager.get_user_info = AsyncMock(return_value=None)

    async with _make_client(app) as client:
        resp = await client.get("/api/auth/status")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json"
    data = resp.json()
    assert "account_a" in data
    assert "account_b" in data
    assert data["account_a"] is None
    assert data["account_b"] is None


@pytest.mark.asyncio
async def test_auth_status_with_authorized_account(monkeypatch):
    """GET /api/auth/status returns AccountInfo for authorized accounts."""
    monkeypatch.setenv("SINGLE_USER_MODE", "true")
    monkeypatch.setenv("TELEGRAM_API_ID", TEST_API_ID)
    monkeypatch.setenv("TELEGRAM_API_HASH", TEST_API_HASH)

    app = _make_app(single_user_mode=True)

    async def mock_get_user_info(account):
        if account == "account_a":
            return {"phone": "+1234567890", "name": "Test User", "username": "testuser"}
        return None

    app.state.session_manager.get_user_info = AsyncMock(side_effect=mock_get_user_info)

    async with _make_client(app) as client:
        resp = await client.get("/api/auth/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["account_a"]["phone"] == "+1234567890"
    assert data["account_a"]["name"] == "Test User"
    assert data["account_b"] is None


# ── POST /api/auth/send-code/{account} ───────────────────────────────


@pytest.mark.asyncio
async def test_send_code_returns_json(monkeypatch):
    """POST /api/auth/send-code/account_a accepts JSON body, returns JSON."""
    monkeypatch.setenv("SINGLE_USER_MODE", "true")
    monkeypatch.setenv("TELEGRAM_API_ID", TEST_API_ID)
    monkeypatch.setenv("TELEGRAM_API_HASH", TEST_API_HASH)

    app = _make_app(single_user_mode=True)
    mock_client = AsyncMock()
    mock_client.is_connected.return_value = True
    mock_sent = MagicMock()
    mock_sent.phone_code_hash = "test_hash_123"
    mock_client.send_code_request = AsyncMock(return_value=mock_sent)
    app.state.session_manager.get_client = MagicMock(return_value=mock_client)

    async with _make_client(app) as client:
        resp = await client.post(
            "/api/auth/send-code/account_a",
            json={"phone": "+1234567890"},
        )

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json"
    data = resp.json()
    assert data["status"] == "code_sent"
    # phone_code_hash must NOT be in the response
    assert "phone_code_hash" not in data


@pytest.mark.asyncio
async def test_send_code_sets_pending_token_cookie(monkeypatch):
    """send-code should set a pending_token cookie for subsequent calls."""
    monkeypatch.setenv("SINGLE_USER_MODE", "true")
    monkeypatch.setenv("TELEGRAM_API_ID", TEST_API_ID)
    monkeypatch.setenv("TELEGRAM_API_HASH", TEST_API_HASH)

    app = _make_app(single_user_mode=True)
    mock_client = AsyncMock()
    mock_client.is_connected.return_value = True
    mock_sent = MagicMock()
    mock_sent.phone_code_hash = "hash_abc"
    mock_client.send_code_request = AsyncMock(return_value=mock_sent)
    app.state.session_manager.get_client = MagicMock(return_value=mock_client)

    async with _make_client(app) as client:
        resp = await client.post(
            "/api/auth/send-code/account_a",
            json={"phone": "+1234567890"},
        )

    assert resp.status_code == 200
    assert "pending_token" in resp.cookies


@pytest.mark.asyncio
async def test_send_code_stores_hash_serverside(monkeypatch):
    """send-code stores phone_code_hash in server-side _pending_auths."""
    monkeypatch.setenv("SINGLE_USER_MODE", "true")
    monkeypatch.setenv("TELEGRAM_API_ID", TEST_API_ID)
    monkeypatch.setenv("TELEGRAM_API_HASH", TEST_API_HASH)

    app = _make_app(single_user_mode=True)
    mock_client = AsyncMock()
    mock_client.is_connected.return_value = True
    mock_sent = MagicMock()
    mock_sent.phone_code_hash = "server_side_hash"
    mock_client.send_code_request = AsyncMock(return_value=mock_sent)
    app.state.session_manager.get_client = MagicMock(return_value=mock_client)

    async with _make_client(app) as client:
        await client.post(
            "/api/auth/send-code/account_a",
            json={"phone": "+1234567890"},
        )

    assert len(_pending_auths) == 1
    pa = next(iter(_pending_auths.values()))
    assert pa.phone_code_hash == "server_side_hash"
    assert pa.phone == "+1234567890"


@pytest.mark.asyncio
async def test_send_code_invalid_phone(monkeypatch):
    """send-code returns 422 for invalid phone numbers."""
    monkeypatch.setenv("SINGLE_USER_MODE", "true")
    monkeypatch.setenv("TELEGRAM_API_ID", TEST_API_ID)
    monkeypatch.setenv("TELEGRAM_API_HASH", TEST_API_HASH)

    app = _make_app(single_user_mode=True)
    mock_client = AsyncMock()
    mock_client.is_connected.return_value = True
    mock_client.send_code_request = AsyncMock(side_effect=_make_telethon_error("PhoneNumberInvalidError"))
    app.state.session_manager.get_client = MagicMock(return_value=mock_client)

    async with _make_client(app) as client:
        resp = await client.post(
            "/api/auth/send-code/account_a",
            json={"phone": "invalid"},
        )

    assert resp.status_code == 422
    assert resp.headers["content-type"] == "application/json"


@pytest.mark.asyncio
async def test_send_code_flood_wait_returns_429(monkeypatch):
    """FloodWaitError returns 429 with wait_seconds."""
    monkeypatch.setenv("SINGLE_USER_MODE", "true")
    monkeypatch.setenv("TELEGRAM_API_ID", TEST_API_ID)
    monkeypatch.setenv("TELEGRAM_API_HASH", TEST_API_HASH)

    app = _make_app(single_user_mode=True)
    mock_client = AsyncMock()
    mock_client.is_connected.return_value = True
    mock_client.send_code_request = AsyncMock(side_effect=_make_flood_wait_error(120))
    app.state.session_manager.get_client = MagicMock(return_value=mock_client)

    async with _make_client(app) as client:
        resp = await client.post(
            "/api/auth/send-code/account_a",
            json={"phone": "+1234567890"},
        )

    assert resp.status_code == 429
    assert resp.headers["content-type"] == "application/json"
    data = resp.json()
    assert data["wait_seconds"] == 120
    assert "detail" in data


# ── POST /api/auth/submit-code/{account} ─────────────────────────────


@pytest.mark.asyncio
async def test_submit_code_success(monkeypatch):
    """submit-code returns success JSON with user info on valid code."""
    monkeypatch.setenv("SINGLE_USER_MODE", "true")
    monkeypatch.setenv("TELEGRAM_API_ID", TEST_API_ID)
    monkeypatch.setenv("TELEGRAM_API_HASH", TEST_API_HASH)

    app = _make_app(single_user_mode=True)
    mock_client = AsyncMock()
    mock_client.sign_in = AsyncMock(return_value=MagicMock())
    app.state.session_manager.get_client = MagicMock(return_value=mock_client)
    app.state.session_manager.get_user_info = AsyncMock(
        return_value={"phone": "+1234567890", "name": "Test", "username": "tst"}
    )

    # Pre-populate pending auth
    _pending_auths["tok123"] = PendingAuth(
        phone="+1234567890",
        phone_code_hash="hash_xyz",
        client=mock_client,
        account="account_a",
        created_at=__import__("time").time(),
    )

    async with _make_client(app) as client:
        resp = await client.post(
            "/api/auth/submit-code/account_a",
            json={"code": "12345"},
            cookies={"pending_token": "tok123"},
        )

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json"
    data = resp.json()
    assert data["status"] == "success"
    assert data["user"]["phone"] == "+1234567890"

    # sign_in should have been called with the server-side phone_code_hash
    mock_client.sign_in.assert_called_once_with("+1234567890", "12345", phone_code_hash="hash_xyz")


@pytest.mark.asyncio
async def test_submit_code_2fa_required(monkeypatch):
    """submit-code returns 2fa_required when SessionPasswordNeededError."""
    monkeypatch.setenv("SINGLE_USER_MODE", "true")
    monkeypatch.setenv("TELEGRAM_API_ID", TEST_API_ID)
    monkeypatch.setenv("TELEGRAM_API_HASH", TEST_API_HASH)

    app = _make_app(single_user_mode=True)
    mock_client = AsyncMock()
    mock_client.sign_in = AsyncMock(side_effect=_make_telethon_error("SessionPasswordNeededError"))
    app.state.session_manager.get_client = MagicMock(return_value=mock_client)

    _pending_auths["tok_2fa"] = PendingAuth(
        phone="+1234567890",
        phone_code_hash="hash_2fa",
        client=mock_client,
        account="account_a",
        created_at=__import__("time").time(),
    )

    async with _make_client(app) as client:
        resp = await client.post(
            "/api/auth/submit-code/account_a",
            json={"code": "12345"},
            cookies={"pending_token": "tok_2fa"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "2fa_required"

    # Pending auth should NOT be cleaned up (needed for 2FA step)
    assert "tok_2fa" in _pending_auths


@pytest.mark.asyncio
async def test_submit_code_no_pending_token(monkeypatch):
    """submit-code returns 400 if no pending_token cookie."""
    monkeypatch.setenv("SINGLE_USER_MODE", "true")
    monkeypatch.setenv("TELEGRAM_API_ID", TEST_API_ID)
    monkeypatch.setenv("TELEGRAM_API_HASH", TEST_API_HASH)

    app = _make_app(single_user_mode=True)

    async with _make_client(app) as client:
        resp = await client.post(
            "/api/auth/submit-code/account_a",
            json={"code": "12345"},
        )

    assert resp.status_code == 400


# ── POST /api/auth/submit-2fa/{account} ──────────────────────────────


@pytest.mark.asyncio
async def test_submit_2fa_success(monkeypatch):
    """submit-2fa returns success JSON on valid password."""
    monkeypatch.setenv("SINGLE_USER_MODE", "true")
    monkeypatch.setenv("TELEGRAM_API_ID", TEST_API_ID)
    monkeypatch.setenv("TELEGRAM_API_HASH", TEST_API_HASH)

    app = _make_app(single_user_mode=True)
    mock_client = AsyncMock()
    mock_client.sign_in = AsyncMock(return_value=MagicMock())
    app.state.session_manager.get_client = MagicMock(return_value=mock_client)
    app.state.session_manager.get_user_info = AsyncMock(
        return_value={"phone": "+1234567890", "name": "Test", "username": None}
    )

    _pending_auths["tok_2fa_ok"] = PendingAuth(
        phone="+1234567890",
        phone_code_hash="hash_2fa",
        client=mock_client,
        account="account_a",
        created_at=__import__("time").time(),
    )

    async with _make_client(app) as client:
        resp = await client.post(
            "/api/auth/submit-2fa/account_a",
            json={"password": "my_2fa_password"},
            cookies={"pending_token": "tok_2fa_ok"},
        )

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json"
    data = resp.json()
    assert data["status"] == "success"
    assert data["user"]["phone"] == "+1234567890"


@pytest.mark.asyncio
async def test_submit_2fa_wrong_password(monkeypatch):
    """submit-2fa returns 422 on incorrect password."""
    monkeypatch.setenv("SINGLE_USER_MODE", "true")
    monkeypatch.setenv("TELEGRAM_API_ID", TEST_API_ID)
    monkeypatch.setenv("TELEGRAM_API_HASH", TEST_API_HASH)

    app = _make_app(single_user_mode=True)
    mock_client = AsyncMock()
    mock_client.sign_in = AsyncMock(side_effect=_make_telethon_error("PasswordHashInvalidError"))
    app.state.session_manager.get_client = MagicMock(return_value=mock_client)

    _pending_auths["tok_bad_pw"] = PendingAuth(
        phone="+1234567890",
        phone_code_hash="hash_2fa",
        client=mock_client,
        account="account_a",
        created_at=__import__("time").time(),
    )

    async with _make_client(app) as client:
        resp = await client.post(
            "/api/auth/submit-2fa/account_a",
            json={"password": "wrong"},
            cookies={"pending_token": "tok_bad_pw"},
        )

    assert resp.status_code == 422
    assert "Incorrect" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_submit_2fa_flood_wait(monkeypatch):
    """submit-2fa returns 429 on FloodWaitError."""
    monkeypatch.setenv("SINGLE_USER_MODE", "true")
    monkeypatch.setenv("TELEGRAM_API_ID", TEST_API_ID)
    monkeypatch.setenv("TELEGRAM_API_HASH", TEST_API_HASH)

    app = _make_app(single_user_mode=True)
    mock_client = AsyncMock()
    mock_client.sign_in = AsyncMock(side_effect=_make_flood_wait_error(60))
    app.state.session_manager.get_client = MagicMock(return_value=mock_client)

    _pending_auths["tok_flood"] = PendingAuth(
        phone="+1234567890",
        phone_code_hash="hash_2fa",
        client=mock_client,
        account="account_a",
        created_at=__import__("time").time(),
    )

    async with _make_client(app) as client:
        resp = await client.post(
            "/api/auth/submit-2fa/account_a",
            json={"password": "test"},
            cookies={"pending_token": "tok_flood"},
        )

    assert resp.status_code == 429
    data = resp.json()
    assert data["wait_seconds"] == 60


# ── POST /api/auth/logout/{account} ──────────────────────────────────


@pytest.mark.asyncio
async def test_logout_returns_json(monkeypatch):
    """POST /api/auth/logout/account_a returns JSON."""
    monkeypatch.setenv("SINGLE_USER_MODE", "true")
    monkeypatch.setenv("TELEGRAM_API_ID", TEST_API_ID)
    monkeypatch.setenv("TELEGRAM_API_HASH", TEST_API_HASH)

    app = _make_app(single_user_mode=True)
    app.state.session_manager.is_authorized = AsyncMock(return_value=False)

    async with _make_client(app) as client:
        resp = await client.post("/api/auth/logout/account_a")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json"
    data = resp.json()
    assert data["status"] == "ok"


# ── Helpers ───────────────────────────────────────────────────────────


def _make_telethon_error(error_name: str):
    """Create a Telethon error by name for use in side_effect."""
    error_cls = getattr(errors, error_name)
    # Telethon errors need a "request" argument
    request = MagicMock()
    request.CONSTRUCTOR_ID = 0
    return error_cls(request)


def _make_flood_wait_error(seconds: int):
    """Create a FloodWaitError with the given wait time."""
    request = MagicMock()
    request.CONSTRUCTOR_ID = 0
    err = errors.FloodWaitError(request, capture=seconds)
    # Ensure .seconds is set correctly
    err.seconds = seconds
    return err
