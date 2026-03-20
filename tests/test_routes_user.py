"""Tests for the user routes (app/routes/user.py).

Uses a minimal FastAPI app with just the user router — same pattern as
test_routes_auth_json.py — to avoid importing app/main.py.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import app.user_context
from app.routes.user import router
from app.user_context import UserContext, register_context

from .conftest import TEST_API_HASH, TEST_API_ID, TEST_SERVER_SECRET

# ── Fixtures ──────────────────────────────────────────────────────────


def _make_app() -> FastAPI:
    """Create a minimal FastAPI app with just the user router."""
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


def _make_client(test_app: FastAPI, cookies: dict | None = None) -> AsyncClient:
    """Create an httpx async test client."""
    return AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
        cookies=cookies,
    )


# ── DELETE /api/user/data ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_user_data_returns_200_and_clears_cookie(monkeypatch, tmp_path):
    """DELETE /api/user/data returns 200 and clears the session_id cookie."""
    monkeypatch.setenv("SINGLE_USER_MODE", "false")
    monkeypatch.setenv("SERVER_SECRET", TEST_SERVER_SECRET)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    # Init the multi-user DB schema
    from app.database import init_db

    await init_db()

    # Register a context so the endpoint can find it
    ctx = UserContext(
        user_id=123,
        session_token="test_token_abc",
        session_manager=None,
        engine=None,
        live_forwarder=None,
    )
    register_context(ctx)

    # Store a session row in the DB so delete_user_session has something to delete
    from app.database import create_user_session, get_db
    from app.middleware import hash_token

    db = await get_db()
    try:
        await create_user_session(
            db,
            user_id=123,
            session_token_hash=hash_token("test_token_abc"),
            encrypted_session_a=None,
            encrypted_session_b=None,
            encrypted_credentials=None,
            encryption_version=1,
            user_agent_hash=None,
            ip_prefix=None,
        )
    finally:
        await db.close()

    test_app = _make_app()
    async with _make_client(test_app, cookies={"session_id": "test_token_abc"}) as client:
        resp = await client.request("DELETE", "/api/user/data")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "deleted"
    # Cookie should be cleared (set to empty or with max-age=0)
    assert "session_id" in resp.headers.get("set-cookie", "")
    # Context should have been removed from registry
    assert len(app.user_context._contexts) == 0


@pytest.mark.asyncio
async def test_delete_user_data_returns_401_without_cookie(monkeypatch):
    """DELETE /api/user/data returns 401 without session_id cookie."""
    monkeypatch.setenv("SINGLE_USER_MODE", "false")
    monkeypatch.setenv("SERVER_SECRET", TEST_SERVER_SECRET)

    test_app = _make_app()
    async with _make_client(test_app) as client:
        resp = await client.request("DELETE", "/api/user/data")

    assert resp.status_code == 401
    assert "authenticated" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_user_data_returns_404_in_single_user_mode(monkeypatch):
    """DELETE /api/user/data returns 404 in single_user_mode."""
    monkeypatch.setenv("SINGLE_USER_MODE", "true")
    monkeypatch.setenv("TELEGRAM_API_ID", TEST_API_ID)
    monkeypatch.setenv("TELEGRAM_API_HASH", TEST_API_HASH)

    test_app = _make_app()
    async with _make_client(test_app, cookies={"session_id": "some_token"}) as client:
        resp = await client.request("DELETE", "/api/user/data")

    assert resp.status_code == 404
    assert "single-user" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_user_data_returns_401_with_expired_session(monkeypatch):
    """DELETE /api/user/data returns 401 when session_id is not in registry."""
    monkeypatch.setenv("SINGLE_USER_MODE", "false")
    monkeypatch.setenv("SERVER_SECRET", TEST_SERVER_SECRET)

    test_app = _make_app()
    async with _make_client(test_app, cookies={"session_id": "nonexistent_token"}) as client:
        resp = await client.request("DELETE", "/api/user/data")

    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_user_data_cancels_engine_and_forwarder(monkeypatch, tmp_path):
    """DELETE /api/user/data cancels active engine and stops live forwarder."""
    monkeypatch.setenv("SINGLE_USER_MODE", "false")
    monkeypatch.setenv("SERVER_SECRET", TEST_SERVER_SECRET)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    from app.database import init_db

    await init_db()

    mock_engine = MagicMock()
    mock_engine.cancel = MagicMock()
    mock_forwarder = AsyncMock()
    mock_forwarder.stop = AsyncMock()

    ctx = UserContext(
        user_id=456,
        session_token="tok_engine",
        session_manager=None,
        engine=mock_engine,
        live_forwarder=mock_forwarder,
    )
    register_context(ctx)

    # Store a session row in the DB
    from app.database import create_user_session, get_db
    from app.middleware import hash_token

    db = await get_db()
    try:
        await create_user_session(
            db,
            user_id=456,
            session_token_hash=hash_token("tok_engine"),
            encrypted_session_a=None,
            encrypted_session_b=None,
            encrypted_credentials=None,
            encryption_version=1,
            user_agent_hash=None,
            ip_prefix=None,
        )
    finally:
        await db.close()

    test_app = _make_app()
    async with _make_client(test_app, cookies={"session_id": "tok_engine"}) as client:
        resp = await client.request("DELETE", "/api/user/data")

    assert resp.status_code == 200
    mock_engine.cancel.assert_called_once()
    mock_forwarder.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_user_data_logs_out_telegram_sessions(monkeypatch, tmp_path):
    """DELETE /api/user/data logs out Telegram sessions via SessionManager."""
    monkeypatch.setenv("SINGLE_USER_MODE", "false")
    monkeypatch.setenv("SERVER_SECRET", TEST_SERVER_SECRET)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    from app.database import init_db

    await init_db()

    mock_sm = AsyncMock()
    mock_sm.is_authorized = AsyncMock(return_value=True)
    mock_client = AsyncMock()
    mock_sm.get_client = MagicMock(return_value=mock_client)
    mock_sm.disconnect_all = AsyncMock()

    ctx = UserContext(
        user_id=789,
        session_token="tok_logout",
        session_manager=mock_sm,
    )
    register_context(ctx)

    from app.database import create_user_session, get_db
    from app.middleware import hash_token

    db = await get_db()
    try:
        await create_user_session(
            db,
            user_id=789,
            session_token_hash=hash_token("tok_logout"),
            encrypted_session_a=None,
            encrypted_session_b=None,
            encrypted_credentials=None,
            encryption_version=1,
            user_agent_hash=None,
            ip_prefix=None,
        )
    finally:
        await db.close()

    test_app = _make_app()
    async with _make_client(test_app, cookies={"session_id": "tok_logout"}) as client:
        resp = await client.request("DELETE", "/api/user/data")

    assert resp.status_code == 200
    # Should have checked authorization for both accounts
    assert mock_sm.is_authorized.call_count == 2
    # Should have called log_out on the client (for both accounts)
    assert mock_client.log_out.call_count == 2
    mock_sm.disconnect_all.assert_awaited_once()
