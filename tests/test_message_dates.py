import aiosqlite
import pytest

from app.database import (
    get_cached_message_dates,
    set_cached_message_dates,
)


@pytest.fixture
async def db(tmp_path):
    db_path = str(tmp_path / "test.db")
    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS chat_date_cache (
            account TEXT NOT NULL,
            chat_id INTEGER NOT NULL,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            dates_json TEXT NOT NULL,
            cached_at TEXT NOT NULL,
            PRIMARY KEY (account, chat_id, year, month)
        );
    """)
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_cache_miss_returns_none(db):
    result = await get_cached_message_dates(db, "account_a", 123, 2026, 3)
    assert result is None


@pytest.mark.asyncio
async def test_cache_roundtrip(db):
    dates = ["2026-03-01", "2026-03-05", "2026-03-10"]
    await set_cached_message_dates(db, "account_a", 123, 2026, 3, dates)
    result = await get_cached_message_dates(db, "account_a", 123, 2026, 3, max_age_hours=24)
    assert result == dates


@pytest.mark.asyncio
async def test_past_month_never_expires(db):
    dates = ["2025-01-15"]
    await set_cached_message_dates(db, "account_a", 123, 2025, 1, dates)
    result = await get_cached_message_dates(db, "account_a", 123, 2025, 1, max_age_hours=0)
    assert result == dates
