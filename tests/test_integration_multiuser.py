"""Integration test: full multi-user flow with mocked Telethon.

Exercises the complete lifecycle across all routers: setup credentials,
auth status, send-code, submit-code, delete user data, concurrent login
blocking, and multi-user isolation.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import app.user_context
from app.routes import auth, chats, live, transfer
from app.routes import setup as setup_routes
from app.routes import user as user_routes
from app.routes.auth import _pending_auths, limiter

from .conftest import TEST_API_HASH, TEST_API_ID, TEST_SERVER_SECRET

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clear_pending_auths():
    """Clear pending auth entries between tests."""
    _pending_auths.clear()
    yield
    _pending_auths.clear()


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset slowapi in-memory rate limit counters between tests."""
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture
async def test_app(tmp_path, monkeypatch):
    """Create a test FastAPI app in multi-user mode with all routers."""
    monkeypatch.setenv("SINGLE_USER_MODE", "false")
    monkeypatch.setenv("SERVER_SECRET", TEST_SERVER_SECRET)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    # Set global Telegram credentials for the auth route's multi-user
    # temp client path (used when no existing pending client exists).
    monkeypatch.setenv("TELEGRAM_API_ID", TEST_API_ID)
    monkeypatch.setenv("TELEGRAM_API_HASH", TEST_API_HASH)

    test_application = FastAPI()
    test_application.include_router(auth.router)
    test_application.include_router(chats.router)
    test_application.include_router(transfer.router)
    test_application.include_router(live.router)
    test_application.include_router(setup_routes.router)
    test_application.include_router(user_routes.router)

    # Initialize DB tables
    from app.database import init_db

    await init_db()

    return test_application


def _make_client(app: FastAPI, cookies: dict | None = None) -> AsyncClient:
    """Create an httpx async test client."""
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies=cookies,
    )


def _mock_telethon_client(user_id=12345, first_name="Test", last_name="User", phone="+1234567890", username="testuser"):
    """Build a mock TelegramClient with common stubs."""
    mock_client = AsyncMock()
    mock_client.is_connected = MagicMock(return_value=True)
    mock_client.connect = AsyncMock()
    mock_client.is_user_authorized = AsyncMock(return_value=True)

    me = MagicMock(
        id=user_id,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        username=username,
    )
    mock_client.get_me = AsyncMock(return_value=me)

    mock_sent = MagicMock()
    mock_sent.phone_code_hash = "hash123"
    mock_client.send_code_request = AsyncMock(return_value=mock_sent)
    mock_client.sign_in = AsyncMock(return_value=me)
    mock_client.log_out = AsyncMock()
    mock_client.disconnect = AsyncMock()

    return mock_client


# ── Helper: perform setup to get session cookie ──────────────────────


async def _do_setup(client: AsyncClient, api_id: int = 12345, api_hash: str = "abc123hash"):
    """POST /api/setup/credentials and return the session_id cookie value."""
    resp = await client.post(
        "/api/setup/credentials",
        json={"api_id": api_id, "api_hash": api_hash},
    )
    assert resp.status_code == 200, f"Setup failed: {resp.text}"
    return resp.cookies.get("session_id")


# ── Test 1: Setup credentials flow ──────────────────────────────────


@pytest.mark.asyncio
async def test_setup_credentials_flow(test_app):
    """POST /api/setup/credentials returns 200 with session cookie set."""
    async with _make_client(test_app) as client:
        resp = await client.post(
            "/api/setup/credentials",
            json={"api_id": 12345, "api_hash": "abc123hash"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "credentials_saved"
    assert "session_id" in resp.cookies

    # Verify a UserContext was registered in the global registry
    assert len(app.user_context._contexts) == 1
    ctx = next(iter(app.user_context._contexts.values()))
    assert ctx.api_id == 12345
    assert ctx.api_hash == "abc123hash"
    assert ctx.session_manager is not None
    assert ctx.rate_limiter is not None


# ── Test 2: Auth status after setup ──────────────────────────────────


@pytest.mark.asyncio
async def test_auth_status_after_setup(test_app):
    """After setup, GET /api/auth/status returns JSON with both accounts null.

    In multi-user mode the auth status route returns None for both
    accounts because no global SessionManager is on app.state.
    """
    async with _make_client(test_app) as client:
        await _do_setup(client)

        resp = await client.get("/api/auth/status")

    assert resp.status_code == 200
    data = resp.json()
    assert "account_a" in data
    assert "account_b" in data
    # In multi-user mode, _get_session_manager returns None so the loop
    # is skipped entirely; both accounts remain null.
    assert data["account_a"] is None
    assert data["account_b"] is None


# ── Test 3: Send code flow ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_code_flow(test_app):
    """Setup then POST /api/auth/send-code/account_a creates a pending token."""
    mock_client = _mock_telethon_client()

    with patch("app.routes.auth.SessionManager") as MockSM:
        mock_sm_instance = MagicMock()
        mock_sm_instance.get_client = MagicMock(return_value=mock_client)
        MockSM.return_value = mock_sm_instance

        async with _make_client(test_app) as client:
            await _do_setup(client)

            resp = await client.post(
                "/api/auth/send-code/account_a",
                json={"phone": "+1234567890"},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "code_sent"
    assert "pending_token" in resp.cookies

    # Verify a pending auth entry was created server-side
    assert len(_pending_auths) == 1
    pa = next(iter(_pending_auths.values()))
    assert pa.phone == "+1234567890"
    assert pa.phone_code_hash == "hash123"
    assert pa.account == "account_a"


# ── Test 4: Full login flow ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_login_flow(test_app):
    """Setup -> send-code -> submit-code -> verify account connected."""
    mock_client = _mock_telethon_client()

    with patch("app.routes.auth.SessionManager") as MockSM:
        mock_sm_instance = MagicMock()
        mock_sm_instance.get_client = MagicMock(return_value=mock_client)
        MockSM.return_value = mock_sm_instance

        async with _make_client(test_app) as client:
            # Step 1: Setup credentials
            await _do_setup(client)

            # Step 2: Send code
            resp = await client.post(
                "/api/auth/send-code/account_a",
                json={"phone": "+1234567890"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "code_sent"

            # Ensure pending_token is forwarded (httpx won't send
            # cookies with Secure flag over plain HTTP in tests).
            pt = resp.cookies.get("pending_token")
            client.cookies.set("pending_token", pt)

            # Step 3: Submit code
            resp = await client.post(
                "/api/auth/submit-code/account_a",
                json={"code": "12345"},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["user"] is not None
    assert data["user"]["phone"] == "+1234567890"
    assert data["user"]["name"] == "Test User"

    # sign_in should have been called with server-side phone_code_hash
    mock_client.sign_in.assert_called_once_with("+1234567890", "12345", phone_code_hash="hash123")

    # Pending auth should be cleaned up after successful login
    assert len(_pending_auths) == 0


# ── Test 5: Delete user data ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_user_data(test_app):
    """Setup -> DELETE /api/user/data -> verify all data cleaned up, cookie cleared."""
    async with _make_client(test_app) as client:
        session_id = await _do_setup(client)

    # Verify the context exists before deletion
    assert len(app.user_context._contexts) == 1

    # Use a new client with the session cookie explicitly set (httpx
    # test clients don't always forward response cookies automatically).
    async with _make_client(test_app, cookies={"session_id": session_id}) as client:
        resp = await client.request("DELETE", "/api/user/data")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "deleted"

    # Context should be removed from registry
    assert len(app.user_context._contexts) == 0

    # Cookie should be cleared (set-cookie header present)
    assert "session_id" in resp.headers.get("set-cookie", "")


# ── Test 6: Concurrent login blocked ─────────────────────────────────


@pytest.mark.asyncio
async def test_concurrent_login_blocked(test_app):
    """send-code for the same phone number twice returns 409 conflict."""
    mock_client = _mock_telethon_client()

    with patch("app.routes.auth.SessionManager") as MockSM:
        mock_sm_instance = MagicMock()
        mock_sm_instance.get_client = MagicMock(return_value=mock_client)
        MockSM.return_value = mock_sm_instance

        async with _make_client(test_app) as client:
            await _do_setup(client)

            # First send-code should succeed
            resp1 = await client.post(
                "/api/auth/send-code/account_a",
                json={"phone": "+1234567890"},
            )
            assert resp1.status_code == 200
            assert resp1.json()["status"] == "code_sent"

        # Second send-code for the same phone (different client session,
        # simulating a concurrent request) should be blocked.
        async with _make_client(test_app) as client2:
            await _do_setup(client2, api_id=99999, api_hash="other_hash")

            resp2 = await client2.post(
                "/api/auth/send-code/account_a",
                json={"phone": "+1234567890"},
            )

    assert resp2.status_code == 409
    assert "already in progress" in resp2.json()["detail"].lower()


# ── Test 7: Multi-user isolation ─────────────────────────────────────


@pytest.mark.asyncio
async def test_multi_user_isolation(test_app):
    """Two users set up independently and have separate UserContexts."""
    # User A sets up
    async with _make_client(test_app) as client_a:
        session_a = await _do_setup(client_a, api_id=11111, api_hash="hash_a")

    # User B sets up
    async with _make_client(test_app) as client_b:
        session_b = await _do_setup(client_b, api_id=22222, api_hash="hash_b")

    # There should be exactly 2 contexts in the registry
    assert len(app.user_context._contexts) == 2

    # Retrieve each context and verify isolation
    ctx_a = app.user_context.get_context(session_a)
    ctx_b = app.user_context.get_context(session_b)

    assert ctx_a is not None
    assert ctx_b is not None
    assert ctx_a is not ctx_b

    # Each context should have its own credentials
    assert ctx_a.api_id == 11111
    assert ctx_a.api_hash == "hash_a"
    assert ctx_b.api_id == 22222
    assert ctx_b.api_hash == "hash_b"

    # Each context should have its own SessionManager and RateLimiter
    assert ctx_a.session_manager is not ctx_b.session_manager
    assert ctx_a.rate_limiter is not ctx_b.rate_limiter

    # Session tokens should be distinct
    assert session_a != session_b
    assert ctx_a.session_token != ctx_b.session_token

    # Deleting User A should not affect User B
    async with _make_client(test_app, cookies={"session_id": session_a}) as client_del:
        resp = await client_del.request("DELETE", "/api/user/data")
    assert resp.status_code == 200

    assert len(app.user_context._contexts) == 1
    assert app.user_context.get_context(session_a) is None
    assert app.user_context.get_context(session_b) is not None
