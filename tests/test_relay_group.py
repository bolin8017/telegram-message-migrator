from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest

from app.database import (
    delete_relay_group_record,
    get_relay_group,
    save_relay_group,
)
from app.telegram_client import SessionManager


@pytest.fixture
async def db(tmp_path):
    db_path = tmp_path / "test.db"
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await conn.executescript(
        """CREATE TABLE IF NOT EXISTS relay_groups (
            user_token TEXT PRIMARY KEY,
            group_id INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );"""
    )
    await conn.commit()
    yield conn
    await conn.close()


@pytest.mark.asyncio
async def test_save_and_get_relay_group(db):
    await save_relay_group(db, "token123", 987654)
    result = await get_relay_group(db, "token123")
    assert result is not None
    assert result["group_id"] == 987654


@pytest.mark.asyncio
async def test_get_relay_group_not_found(db):
    result = await get_relay_group(db, "nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_delete_relay_group_record(db):
    await save_relay_group(db, "token123", 987654)
    await delete_relay_group_record(db, "token123")
    result = await get_relay_group(db, "token123")
    assert result is None


@pytest.mark.asyncio
async def test_save_relay_group_upsert(db):
    await save_relay_group(db, "token123", 111)
    await save_relay_group(db, "token123", 222)
    result = await get_relay_group(db, "token123")
    assert result["group_id"] == 222


# ---------------------------------------------------------------------------
# SessionManager relay group lifecycle tests
# ---------------------------------------------------------------------------


def _make_session_manager():
    sm = SessionManager(api_id=99999, api_hash="test_hash")
    sm._clients["account_a"] = MagicMock()
    sm._clients["account_b"] = MagicMock()
    return sm


@pytest.mark.asyncio
async def test_ensure_relay_group_creates_and_caches():
    sm = _make_session_manager()
    mock_entity_a = MagicMock()
    mock_entity_b = MagicMock()

    mock_result = MagicMock()
    mock_result.chats = [MagicMock(id=123456)]
    sm._clients["account_a"].__call__ = AsyncMock(
        side_effect=[
            mock_result,  # CreateChannelRequest
            MagicMock(link="https://t.me/+abc123"),  # ExportChatInviteRequest
        ]
    )
    sm._clients["account_a"].get_entity = AsyncMock(return_value=mock_entity_a)

    sm._clients["account_b"].__call__ = AsyncMock()  # ImportChatInviteRequest
    sm._clients["account_b"].get_entity = AsyncMock(return_value=mock_entity_b)

    relay_a, relay_b = await sm.ensure_relay_group()
    assert relay_a is mock_entity_a
    assert relay_b is mock_entity_b

    # Second call returns cached
    relay_a2, relay_b2 = await sm.ensure_relay_group()
    assert relay_a2 is mock_entity_a


@pytest.mark.asyncio
async def test_ensure_relay_group_idempotent_with_lock():
    sm = _make_session_manager()
    sm._relay_entity_a = MagicMock()
    sm._relay_entity_b = MagicMock()
    sm._relay_group_id = 999

    relay_a, relay_b = await sm.ensure_relay_group()
    assert relay_a is sm._relay_entity_a
    assert relay_b is sm._relay_entity_b


@pytest.mark.asyncio
async def test_ensure_relay_group_persists_to_db(db):
    sm = _make_session_manager()
    mock_entity_a = MagicMock()
    mock_entity_b = MagicMock()

    mock_result = MagicMock()
    mock_result.chats = [MagicMock(id=123456)]
    sm._clients["account_a"].__call__ = AsyncMock(
        side_effect=[
            mock_result,
            MagicMock(link="https://t.me/+abc123"),
        ]
    )
    sm._clients["account_a"].get_entity = AsyncMock(return_value=mock_entity_a)
    sm._clients["account_b"].__call__ = AsyncMock()
    sm._clients["account_b"].get_entity = AsyncMock(return_value=mock_entity_b)

    await sm.ensure_relay_group(db=db, user_token="token123")

    result = await get_relay_group(db, "token123")
    assert result is not None
    assert result["group_id"] == 123456


@pytest.mark.asyncio
async def test_cleanup_relay_messages_best_effort():
    sm = _make_session_manager()
    sm._relay_group_id = 123456
    sm._relay_entity_a = MagicMock()

    sm._clients["account_a"].__call__ = AsyncMock(side_effect=Exception("API error"))
    await sm.cleanup_relay_messages([1, 2, 3])  # should not raise


@pytest.mark.asyncio
async def test_delete_relay_group():
    sm = _make_session_manager()
    sm._relay_group_id = 123456
    sm._relay_entity_a = MagicMock()
    sm._relay_entity_b = MagicMock()
    sm._clients["account_a"].__call__ = AsyncMock()

    await sm.delete_relay_group()
    assert sm._relay_group_id is None
    assert sm._relay_entity_a is None
    assert sm._relay_entity_b is None
