"""Tests for the setup routes (app/routes/setup.py).

Uses a minimal FastAPI app with just the setup router — same pattern as
test_routes_auth_json.py — to avoid importing app/main.py.
"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import app.user_context
from app.routes.setup import router

from .conftest import TEST_API_HASH, TEST_API_ID, TEST_SERVER_SECRET

# ── Fixtures ──────────────────────────────────────────────────────────


def _make_app() -> FastAPI:
    """Create a minimal FastAPI app with just the setup router."""
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


def _make_client(test_app: FastAPI) -> AsyncClient:
    """Create an httpx async test client."""
    return AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    )


# ── POST /api/setup/credentials ──────────────────────────────────────


@pytest.mark.asyncio
async def test_setup_credentials_returns_200_and_sets_cookie(monkeypatch, tmp_path):
    """POST /api/setup/credentials returns 200 + sets session_id cookie."""
    monkeypatch.setenv("SINGLE_USER_MODE", "false")
    monkeypatch.setenv("SERVER_SECRET", TEST_SERVER_SECRET)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    # Init the multi-user DB schema so the table exists
    from app.database import init_db

    await init_db()

    test_app = _make_app()
    async with _make_client(test_app) as client:
        resp = await client.post(
            "/api/setup/credentials",
            json={"api_id": 12345, "api_hash": "abc123hash"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "credentials_saved"
    assert "session_id" in resp.cookies


@pytest.mark.asyncio
async def test_setup_credentials_returns_404_in_single_user_mode(monkeypatch):
    """POST /api/setup/credentials returns 404 in single_user_mode."""
    monkeypatch.setenv("SINGLE_USER_MODE", "true")
    monkeypatch.setenv("TELEGRAM_API_ID", TEST_API_ID)
    monkeypatch.setenv("TELEGRAM_API_HASH", TEST_API_HASH)

    test_app = _make_app()
    async with _make_client(test_app) as client:
        resp = await client.post(
            "/api/setup/credentials",
            json={"api_id": 12345, "api_hash": "abc123hash"},
        )

    assert resp.status_code == 404
    assert "single-user" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_setup_credentials_missing_fields_returns_422(monkeypatch):
    """POST /api/setup/credentials with missing fields returns 422."""
    monkeypatch.setenv("SINGLE_USER_MODE", "false")
    monkeypatch.setenv("SERVER_SECRET", TEST_SERVER_SECRET)

    test_app = _make_app()
    async with _make_client(test_app) as client:
        # Missing api_hash
        resp = await client.post(
            "/api/setup/credentials",
            json={"api_id": 12345},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_setup_credentials_invalid_api_id_returns_422(monkeypatch):
    """POST /api/setup/credentials with non-integer api_id returns 422."""
    monkeypatch.setenv("SINGLE_USER_MODE", "false")
    monkeypatch.setenv("SERVER_SECRET", TEST_SERVER_SECRET)

    test_app = _make_app()
    async with _make_client(test_app) as client:
        resp = await client.post(
            "/api/setup/credentials",
            json={"api_id": "not_a_number", "api_hash": "abc123"},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_setup_credentials_registers_user_context(monkeypatch, tmp_path):
    """POST /api/setup/credentials registers a UserContext in the registry."""
    monkeypatch.setenv("SINGLE_USER_MODE", "false")
    monkeypatch.setenv("SERVER_SECRET", TEST_SERVER_SECRET)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    from app.database import init_db

    await init_db()

    test_app = _make_app()
    async with _make_client(test_app) as client:
        resp = await client.post(
            "/api/setup/credentials",
            json={"api_id": 99999, "api_hash": "hashvalue"},
        )

    assert resp.status_code == 200
    # Verify a context was registered
    assert len(app.user_context._contexts) == 1
    ctx = next(iter(app.user_context._contexts.values()))
    assert ctx.api_id == 99999
    assert ctx.api_hash == "hashvalue"
    assert ctx.session_manager is not None
    assert ctx.rate_limiter is not None


@pytest.mark.asyncio
async def test_setup_credentials_returns_503_when_registry_full(monkeypatch, tmp_path):
    """POST /api/setup/credentials returns 503 when context registry is full."""
    monkeypatch.setenv("SINGLE_USER_MODE", "false")
    monkeypatch.setenv("SERVER_SECRET", TEST_SERVER_SECRET)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    # Set a very low limit so the registry is immediately full
    monkeypatch.setenv("MAX_USER_CONTEXTS", "0")

    from app.database import init_db

    await init_db()

    test_app = _make_app()
    async with _make_client(test_app) as client:
        resp = await client.post(
            "/api/setup/credentials",
            json={"api_id": 12345, "api_hash": "abc123"},
        )

    assert resp.status_code == 503
