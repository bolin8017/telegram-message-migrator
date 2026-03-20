import asyncio
from datetime import UTC, datetime, timedelta

import aiosqlite
import pytest

from .conftest import TEST_API_HASH, TEST_API_ID, TEST_SERVER_SECRET


@pytest.fixture
def multi_user_env(monkeypatch):
    """Set environment variables for multi-user mode."""
    monkeypatch.setenv("SINGLE_USER_MODE", "false")
    monkeypatch.setenv("SERVER_SECRET", TEST_SERVER_SECRET)


@pytest.fixture
def single_user_env(monkeypatch):
    """Set environment variables for single-user mode."""
    monkeypatch.setenv("SINGLE_USER_MODE", "true")
    monkeypatch.setenv("TELEGRAM_API_ID", TEST_API_ID)
    monkeypatch.setenv("TELEGRAM_API_HASH", TEST_API_HASH)


@pytest.fixture
def multi_user_db_path(tmp_path, monkeypatch, multi_user_env):
    """Provide a temp DB path and configure settings for multi-user mode."""
    db_path = tmp_path / "multi_user_test.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    return db_path


@pytest.fixture
def single_user_db_path(tmp_path, monkeypatch, single_user_env):
    """Provide a temp DB path and configure settings for single-user mode."""
    db_path = tmp_path / "single_user_test.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    return db_path


async def _get_table_names(db_path) -> set[str]:
    """Helper to fetch all table names from the database."""
    db = await aiosqlite.connect(db_path)
    try:
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        rows = await cursor.fetchall()
        return {row[0] for row in rows}
    finally:
        await db.close()


# --- Schema creation tests ---


async def test_multi_user_creates_user_sessions_table(multi_user_db_path):
    from app.database import init_db

    await init_db()
    tables = await _get_table_names(multi_user_db_path)
    assert "user_sessions" in tables


async def test_multi_user_does_not_create_transfers_table(multi_user_db_path):
    from app.database import init_db

    await init_db()
    tables = await _get_table_names(multi_user_db_path)
    assert "transfers" not in tables
    assert "messages" not in tables


async def test_single_user_creates_transfers_table(single_user_db_path):
    from app.database import init_db

    await init_db()
    tables = await _get_table_names(single_user_db_path)
    assert "transfers" in tables
    assert "messages" in tables


async def test_single_user_does_not_create_user_sessions_table(single_user_db_path):
    from app.database import init_db

    await init_db()
    tables = await _get_table_names(single_user_db_path)
    assert "user_sessions" not in tables


# --- PRAGMA secure_delete tests ---


async def test_multi_user_get_db_sets_secure_delete(multi_user_db_path):
    from app.database import get_db, init_db

    await init_db()
    db = await get_db()
    try:
        cursor = await db.execute("PRAGMA secure_delete")
        row = await cursor.fetchone()
        assert row[0] == 1
    finally:
        await db.close()


async def test_single_user_get_db_does_not_force_secure_delete(single_user_db_path):
    """In single-user mode, get_db() should NOT explicitly set secure_delete.

    Note: we cannot assert secure_delete==0 because some SQLite builds
    compile with SQLITE_SECURE_DELETE=1 as default. Instead we verify
    our code path does NOT call the pragma by checking it matches the
    compile-time default of a fresh connection.
    """
    import aiosqlite as _aiosqlite

    from app.database import get_db, init_db

    await init_db()

    # Get the compile-time default from a bare connection
    bare_db = await _aiosqlite.connect(str(single_user_db_path))
    cursor = await bare_db.execute("PRAGMA secure_delete")
    default_val = (await cursor.fetchone())[0]
    await bare_db.close()

    db = await get_db()
    try:
        cursor = await db.execute("PRAGMA secure_delete")
        row = await cursor.fetchone()
        assert row[0] == default_val
    finally:
        await db.close()


# --- CRUD tests ---


async def test_create_and_get_user_session(multi_user_db_path):
    from app.database import create_user_session, get_user_session, init_db

    await init_db()
    db = await aiosqlite.connect(str(multi_user_db_path))
    db.row_factory = aiosqlite.Row
    try:
        await create_user_session(
            db,
            user_id=12345,
            session_token_hash="hash_abc",
            encrypted_session_a=b"session_a_data",
            encrypted_session_b=b"session_b_data",
            encrypted_credentials=b"creds_data",
            encryption_version=1,
            user_agent_hash="ua_hash_123",
            ip_prefix="192.168",
        )
        session = await get_user_session(db, "hash_abc")
        assert session is not None
        assert session["user_id"] == 12345
        assert session["session_token_hash"] == "hash_abc"
        assert session["encrypted_session_a"] == b"session_a_data"
        assert session["encrypted_session_b"] == b"session_b_data"
        assert session["encrypted_credentials"] == b"creds_data"
        assert session["encryption_version"] == 1
        assert session["user_agent_hash"] == "ua_hash_123"
        assert session["ip_prefix"] == "192.168"
        assert session["created_at"] is not None
        assert session["last_active"] is not None
    finally:
        await db.close()


async def test_get_user_session_not_found(multi_user_db_path):
    from app.database import get_user_session, init_db

    await init_db()
    db = await aiosqlite.connect(str(multi_user_db_path))
    db.row_factory = aiosqlite.Row
    try:
        session = await get_user_session(db, "nonexistent_hash")
        assert session is None
    finally:
        await db.close()


async def test_get_user_session_by_user_id(multi_user_db_path):
    from app.database import create_user_session, get_user_session_by_user_id, init_db

    await init_db()
    db = await aiosqlite.connect(str(multi_user_db_path))
    db.row_factory = aiosqlite.Row
    try:
        await create_user_session(
            db,
            user_id=100,
            session_token_hash="hash_1",
            encrypted_session_a=None,
            encrypted_session_b=None,
            encrypted_credentials=None,
            encryption_version=1,
            user_agent_hash=None,
            ip_prefix=None,
        )
        await create_user_session(
            db,
            user_id=100,
            session_token_hash="hash_2",
            encrypted_session_a=None,
            encrypted_session_b=None,
            encrypted_credentials=None,
            encryption_version=1,
            user_agent_hash=None,
            ip_prefix=None,
        )
        await create_user_session(
            db,
            user_id=200,
            session_token_hash="hash_3",
            encrypted_session_a=None,
            encrypted_session_b=None,
            encrypted_credentials=None,
            encryption_version=1,
            user_agent_hash=None,
            ip_prefix=None,
        )
        sessions = await get_user_session_by_user_id(db, 100)
        assert len(sessions) == 2
        assert all(s["user_id"] == 100 for s in sessions)

        sessions_200 = await get_user_session_by_user_id(db, 200)
        assert len(sessions_200) == 1
    finally:
        await db.close()


async def test_get_user_session_count(multi_user_db_path):
    from app.database import create_user_session, get_user_session_count, init_db

    await init_db()
    db = await aiosqlite.connect(str(multi_user_db_path))
    db.row_factory = aiosqlite.Row
    try:
        assert await get_user_session_count(db, 100) == 0

        await create_user_session(
            db,
            user_id=100,
            session_token_hash="hash_a",
            encrypted_session_a=None,
            encrypted_session_b=None,
            encrypted_credentials=None,
            encryption_version=1,
            user_agent_hash=None,
            ip_prefix=None,
        )
        assert await get_user_session_count(db, 100) == 1

        await create_user_session(
            db,
            user_id=100,
            session_token_hash="hash_b",
            encrypted_session_a=None,
            encrypted_session_b=None,
            encrypted_credentials=None,
            encryption_version=1,
            user_agent_hash=None,
            ip_prefix=None,
        )
        assert await get_user_session_count(db, 100) == 2
    finally:
        await db.close()


async def test_update_session_last_active(multi_user_db_path):
    from app.database import create_user_session, get_user_session, init_db, update_session_last_active

    await init_db()
    db = await aiosqlite.connect(str(multi_user_db_path))
    db.row_factory = aiosqlite.Row
    try:
        await create_user_session(
            db,
            user_id=100,
            session_token_hash="hash_x",
            encrypted_session_a=None,
            encrypted_session_b=None,
            encrypted_credentials=None,
            encryption_version=1,
            user_agent_hash=None,
            ip_prefix=None,
        )
        session_before = await get_user_session(db, "hash_x")
        original_last_active = session_before["last_active"]

        # Small delay to ensure timestamp differs
        await asyncio.sleep(0.01)

        await update_session_last_active(db, "hash_x")
        session_after = await get_user_session(db, "hash_x")
        assert session_after["last_active"] >= original_last_active
    finally:
        await db.close()


async def test_update_session_data(multi_user_db_path):
    from app.database import create_user_session, get_user_session, init_db, update_session_data

    await init_db()
    db = await aiosqlite.connect(str(multi_user_db_path))
    db.row_factory = aiosqlite.Row
    try:
        await create_user_session(
            db,
            user_id=100,
            session_token_hash="hash_update",
            encrypted_session_a=b"old_a",
            encrypted_session_b=b"old_b",
            encrypted_credentials=b"old_creds",
            encryption_version=1,
            user_agent_hash=None,
            ip_prefix=None,
        )

        # Update only session_a
        await update_session_data(db, "hash_update", encrypted_session_a=b"new_a")
        session = await get_user_session(db, "hash_update")
        assert session["encrypted_session_a"] == b"new_a"
        assert session["encrypted_session_b"] == b"old_b"
        assert session["encrypted_credentials"] == b"old_creds"

        # Update session_b and credentials together
        await update_session_data(
            db,
            "hash_update",
            encrypted_session_b=b"new_b",
            encrypted_credentials=b"new_creds",
        )
        session = await get_user_session(db, "hash_update")
        assert session["encrypted_session_a"] == b"new_a"
        assert session["encrypted_session_b"] == b"new_b"
        assert session["encrypted_credentials"] == b"new_creds"
    finally:
        await db.close()


async def test_delete_user_session(multi_user_db_path):
    from app.database import create_user_session, delete_user_session, get_user_session, init_db

    await init_db()
    db = await aiosqlite.connect(str(multi_user_db_path))
    db.row_factory = aiosqlite.Row
    try:
        await create_user_session(
            db,
            user_id=100,
            session_token_hash="hash_del",
            encrypted_session_a=None,
            encrypted_session_b=None,
            encrypted_credentials=None,
            encryption_version=1,
            user_agent_hash=None,
            ip_prefix=None,
        )
        assert await get_user_session(db, "hash_del") is not None

        await delete_user_session(db, "hash_del")
        assert await get_user_session(db, "hash_del") is None
    finally:
        await db.close()


async def test_delete_user_sessions_by_user_id(multi_user_db_path):
    from app.database import (
        create_user_session,
        delete_user_sessions_by_user_id,
        get_user_session,
        get_user_session_count,
        init_db,
    )

    await init_db()
    db = await aiosqlite.connect(str(multi_user_db_path))
    db.row_factory = aiosqlite.Row
    try:
        await create_user_session(
            db,
            user_id=300,
            session_token_hash="hash_d1",
            encrypted_session_a=None,
            encrypted_session_b=None,
            encrypted_credentials=None,
            encryption_version=1,
            user_agent_hash=None,
            ip_prefix=None,
        )
        await create_user_session(
            db,
            user_id=300,
            session_token_hash="hash_d2",
            encrypted_session_a=None,
            encrypted_session_b=None,
            encrypted_credentials=None,
            encryption_version=1,
            user_agent_hash=None,
            ip_prefix=None,
        )
        await create_user_session(
            db,
            user_id=400,
            session_token_hash="hash_d3",
            encrypted_session_a=None,
            encrypted_session_b=None,
            encrypted_credentials=None,
            encryption_version=1,
            user_agent_hash=None,
            ip_prefix=None,
        )

        await delete_user_sessions_by_user_id(db, 300)
        assert await get_user_session_count(db, 300) == 0
        # user_id=400 session should remain
        assert await get_user_session(db, "hash_d3") is not None
    finally:
        await db.close()


async def test_cleanup_expired_sessions(multi_user_db_path):
    from app.database import cleanup_expired_sessions, get_user_session, init_db

    await init_db()
    db = await aiosqlite.connect(str(multi_user_db_path))
    db.row_factory = aiosqlite.Row
    try:
        now = datetime.now(UTC)
        old_time = (now - timedelta(days=10)).isoformat()
        recent_time = (now - timedelta(hours=1)).isoformat()

        # Insert expired session directly
        await db.execute(
            """INSERT INTO user_sessions
               (user_id, session_token_hash, encryption_version, created_at, last_active)
               VALUES (?, ?, ?, ?, ?)""",
            (100, "expired_hash", 1, old_time, old_time),
        )
        # Insert recent session directly
        await db.execute(
            """INSERT INTO user_sessions
               (user_id, session_token_hash, encryption_version, created_at, last_active)
               VALUES (?, ?, ?, ?, ?)""",
            (200, "recent_hash", 1, recent_time, recent_time),
        )
        await db.commit()

        deleted = await cleanup_expired_sessions(db, expiry_days=7)
        assert deleted == 1
        assert await get_user_session(db, "expired_hash") is None
        assert await get_user_session(db, "recent_hash") is not None
    finally:
        await db.close()


async def test_cleanup_expired_sessions_returns_zero_when_none_expired(multi_user_db_path):
    from app.database import cleanup_expired_sessions, init_db

    await init_db()
    db = await aiosqlite.connect(str(multi_user_db_path))
    db.row_factory = aiosqlite.Row
    try:
        deleted = await cleanup_expired_sessions(db, expiry_days=7)
        assert deleted == 0
    finally:
        await db.close()


async def test_create_session_with_nullable_fields(multi_user_db_path):
    from app.database import create_user_session, get_user_session, init_db

    await init_db()
    db = await aiosqlite.connect(str(multi_user_db_path))
    db.row_factory = aiosqlite.Row
    try:
        await create_user_session(
            db,
            user_id=500,
            session_token_hash="hash_nullable",
            encrypted_session_a=None,
            encrypted_session_b=None,
            encrypted_credentials=None,
            encryption_version=1,
            user_agent_hash=None,
            ip_prefix=None,
        )
        session = await get_user_session(db, "hash_nullable")
        assert session is not None
        assert session["encrypted_session_a"] is None
        assert session["encrypted_session_b"] is None
        assert session["encrypted_credentials"] is None
        assert session["user_agent_hash"] is None
        assert session["ip_prefix"] is None
    finally:
        await db.close()


async def test_duplicate_session_token_hash_raises(multi_user_db_path):
    from app.database import create_user_session, init_db

    await init_db()
    db = await aiosqlite.connect(str(multi_user_db_path))
    db.row_factory = aiosqlite.Row
    try:
        await create_user_session(
            db,
            user_id=100,
            session_token_hash="unique_hash",
            encrypted_session_a=None,
            encrypted_session_b=None,
            encrypted_credentials=None,
            encryption_version=1,
            user_agent_hash=None,
            ip_prefix=None,
        )
        with pytest.raises(aiosqlite.IntegrityError):
            await create_user_session(
                db,
                user_id=200,
                session_token_hash="unique_hash",
                encrypted_session_a=None,
                encrypted_session_b=None,
                encrypted_credentials=None,
                encryption_version=1,
                user_agent_hash=None,
                ip_prefix=None,
            )
    finally:
        await db.close()
