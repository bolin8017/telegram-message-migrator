import json
from datetime import UTC, datetime, timedelta

import aiosqlite

from .config import get_settings

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS transfers (
    id TEXT PRIMARY KEY,
    source_chat_id INTEGER NOT NULL,
    dest_chat_id INTEGER,
    mode TEXT NOT NULL DEFAULT 'forward',
    target_type TEXT NOT NULL DEFAULT 'saved_messages',
    status TEXT NOT NULL DEFAULT 'pending',
    config_json TEXT NOT NULL DEFAULT '{}',
    total_messages INTEGER NOT NULL DEFAULT 0,
    transferred_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transfer_id TEXT NOT NULL REFERENCES transfers(id),
    source_msg_id INTEGER NOT NULL,
    dest_msg_id INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(transfer_id, source_msg_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_transfer ON messages(transfer_id);
CREATE INDEX IF NOT EXISTS idx_messages_status ON messages(transfer_id, status);
"""

_MULTI_USER_TABLES = """
CREATE TABLE IF NOT EXISTS user_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    session_token_hash TEXT NOT NULL UNIQUE,
    encrypted_session_a BLOB,
    encrypted_session_b BLOB,
    encrypted_credentials BLOB,
    encryption_version INTEGER NOT NULL DEFAULT 1,
    user_agent_hash TEXT,
    ip_prefix TEXT,
    created_at TEXT NOT NULL,
    last_active TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_last_active ON user_sessions(last_active);
"""

_RELAY_GROUPS_TABLE = """
CREATE TABLE IF NOT EXISTS relay_groups (
    user_token TEXT PRIMARY KEY,
    group_id   INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
"""

_CHAT_DATE_CACHE_TABLE = """
CREATE TABLE IF NOT EXISTS chat_date_cache (
    account TEXT NOT NULL,
    chat_id INTEGER NOT NULL,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    dates_json TEXT NOT NULL,
    cached_at TEXT NOT NULL,
    PRIMARY KEY (account, chat_id, year, month)
);
"""


async def get_db() -> aiosqlite.Connection:
    settings = get_settings()
    db = await aiosqlite.connect(settings.db_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys=ON")
    if not settings.single_user_mode:
        await db.execute("PRAGMA secure_delete=ON")
    return db


async def init_db() -> None:
    settings = get_settings()
    db = await aiosqlite.connect(settings.db_path)
    try:
        await db.execute("PRAGMA journal_mode=WAL")
        if settings.single_user_mode:
            await db.executescript(_CREATE_TABLES)
            await db.executescript(_CHAT_DATE_CACHE_TABLE)
            # Mark stale "running"/"paused" jobs as cancelled on startup
            # (these were interrupted by a server restart)
            await db.execute(
                "UPDATE transfers SET status='cancelled', updated_at=? WHERE status IN ('running', 'paused')",
                (_now(),),
            )
        else:
            await db.execute("PRAGMA secure_delete=ON")
            await db.executescript(_MULTI_USER_TABLES)
            await db.executescript(_RELAY_GROUPS_TABLE)
            await db.executescript(_CHAT_DATE_CACHE_TABLE)
        await db.commit()
    finally:
        await db.close()


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def create_transfer(
    db: aiosqlite.Connection,
    transfer_id: str,
    source_chat_id: int,
    dest_chat_id: int | None,
    mode: str,
    target_type: str,
    config: dict,
) -> None:
    await db.execute(
        """INSERT INTO transfers
           (id, source_chat_id, dest_chat_id, mode, target_type, config_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (transfer_id, source_chat_id, dest_chat_id, mode, target_type, json.dumps(config), _now(), _now()),
    )
    await db.commit()


async def update_transfer_status(
    db: aiosqlite.Connection,
    transfer_id: str,
    status: str,
    **counters: int,
) -> None:
    sets = ["status = ?", "updated_at = ?"]
    vals: list = [status, _now()]
    for col in ("total_messages", "transferred_count", "failed_count", "skipped_count"):
        if col in counters:
            sets.append(f"{col} = ?")
            vals.append(counters[col])
    vals.append(transfer_id)
    await db.execute(f"UPDATE transfers SET {', '.join(sets)} WHERE id = ?", vals)
    await db.commit()


async def record_message(
    db: aiosqlite.Connection,
    transfer_id: str,
    source_msg_id: int,
    status: str,
    dest_msg_id: int | None = None,
    error: str | None = None,
) -> None:
    await db.execute(
        """INSERT INTO messages (transfer_id, source_msg_id, dest_msg_id, status, error, created_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(transfer_id, source_msg_id) DO UPDATE SET
             status=excluded.status, dest_msg_id=excluded.dest_msg_id,
             error=excluded.error""",
        (transfer_id, source_msg_id, dest_msg_id, status, error, _now()),
    )


async def get_processed_msg_ids(db: aiosqlite.Connection, transfer_id: str) -> set[int]:
    cursor = await db.execute(
        "SELECT source_msg_id FROM messages WHERE transfer_id = ? AND status IN ('done', 'skipped')",
        (transfer_id,),
    )
    rows = await cursor.fetchall()
    return {row[0] for row in rows}


async def get_all_done_msg_ids_for_chat(
    db: aiosqlite.Connection,
    source_chat_id: int,
    dest_chat_id: int | None = None,
) -> set[int]:
    """Get all successfully transferred message IDs across ALL jobs for a source→dest pair.
    When dest_chat_id is provided, only deduplicates against jobs targeting the same
    destination — allowing the same source messages to be sent to different targets."""
    if dest_chat_id is not None:
        cursor = await db.execute(
            """SELECT m.source_msg_id FROM messages m
               JOIN transfers t ON m.transfer_id = t.id
               WHERE t.source_chat_id = ? AND t.dest_chat_id = ? AND m.status = 'done'""",
            (source_chat_id, dest_chat_id),
        )
    else:
        cursor = await db.execute(
            """SELECT m.source_msg_id FROM messages m
               JOIN transfers t ON m.transfer_id = t.id
               WHERE t.source_chat_id = ? AND m.status = 'done'""",
            (source_chat_id,),
        )
    rows = await cursor.fetchall()
    return {row[0] for row in rows}


async def get_transfer_history(db: aiosqlite.Connection, limit: int = 50, offset: int = 0) -> list[dict]:
    cursor = await db.execute(
        """SELECT id, source_chat_id, dest_chat_id, mode, target_type,
                  status, total_messages, transferred_count, failed_count, skipped_count,
                  created_at, updated_at
           FROM transfers ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        (limit, offset),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def get_transfer_count(db: aiosqlite.Connection) -> int:
    cursor = await db.execute("SELECT COUNT(*) FROM transfers")
    row = await cursor.fetchone()
    return row[0] if row else 0


# ---------------------------------------------------------------------------
# Multi-user session CRUD
# ---------------------------------------------------------------------------


async def create_user_session(
    db: aiosqlite.Connection,
    user_id: int,
    session_token_hash: str,
    encrypted_session_a: bytes | None,
    encrypted_session_b: bytes | None,
    encrypted_credentials: bytes | None,
    encryption_version: int,
    user_agent_hash: str | None,
    ip_prefix: str | None,
) -> None:
    now = _now()
    await db.execute(
        """INSERT INTO user_sessions
           (user_id, session_token_hash, encrypted_session_a, encrypted_session_b,
            encrypted_credentials, encryption_version, user_agent_hash, ip_prefix,
            created_at, last_active)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            session_token_hash,
            encrypted_session_a,
            encrypted_session_b,
            encrypted_credentials,
            encryption_version,
            user_agent_hash,
            ip_prefix,
            now,
            now,
        ),
    )
    await db.commit()


async def get_user_session(db: aiosqlite.Connection, session_token_hash: str) -> dict | None:
    cursor = await db.execute(
        "SELECT * FROM user_sessions WHERE session_token_hash = ?",
        (session_token_hash,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_user_session_by_user_id(db: aiosqlite.Connection, user_id: int) -> list[dict]:
    cursor = await db.execute(
        "SELECT * FROM user_sessions WHERE user_id = ? ORDER BY last_active DESC",
        (user_id,),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def get_user_session_count(db: aiosqlite.Connection, user_id: int) -> int:
    cursor = await db.execute(
        "SELECT COUNT(*) FROM user_sessions WHERE user_id = ?",
        (user_id,),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


async def update_session_last_active(db: aiosqlite.Connection, session_token_hash: str) -> None:
    await db.execute(
        "UPDATE user_sessions SET last_active = ? WHERE session_token_hash = ?",
        (_now(), session_token_hash),
    )
    await db.commit()


async def upgrade_session_user_id(
    db: aiosqlite.Connection,
    session_token_hash: str,
    new_user_id: int,
    encrypted_credentials: bytes,
    encrypted_session_a: bytes | None = None,
    encrypted_session_b: bytes | None = None,
) -> None:
    """Update user_id and re-encrypted data after Telegram login.

    Called when the temporary user_id (derived from session token) is
    replaced with the real Telegram user ID.
    """
    sets = ["user_id = ?", "encrypted_credentials = ?", "last_active = ?"]
    vals: list = [new_user_id, encrypted_credentials, _now()]
    if encrypted_session_a is not None:
        sets.append("encrypted_session_a = ?")
        vals.append(encrypted_session_a)
    if encrypted_session_b is not None:
        sets.append("encrypted_session_b = ?")
        vals.append(encrypted_session_b)
    vals.append(session_token_hash)
    await db.execute(
        f"UPDATE user_sessions SET {', '.join(sets)} WHERE session_token_hash = ?",
        vals,
    )
    await db.commit()


async def update_session_data(
    db: aiosqlite.Connection,
    session_token_hash: str,
    encrypted_session_a: bytes | None = None,
    encrypted_session_b: bytes | None = None,
    encrypted_credentials: bytes | None = None,
) -> None:
    sets: list[str] = []
    vals: list = []
    if encrypted_session_a is not None:
        sets.append("encrypted_session_a = ?")
        vals.append(encrypted_session_a)
    if encrypted_session_b is not None:
        sets.append("encrypted_session_b = ?")
        vals.append(encrypted_session_b)
    if encrypted_credentials is not None:
        sets.append("encrypted_credentials = ?")
        vals.append(encrypted_credentials)
    if not sets:
        return
    sets.append("last_active = ?")
    vals.append(_now())
    vals.append(session_token_hash)
    await db.execute(
        f"UPDATE user_sessions SET {', '.join(sets)} WHERE session_token_hash = ?",
        vals,
    )
    await db.commit()


async def delete_user_session(db: aiosqlite.Connection, session_token_hash: str) -> None:
    await db.execute(
        "DELETE FROM user_sessions WHERE session_token_hash = ?",
        (session_token_hash,),
    )
    await db.commit()


async def delete_user_sessions_by_user_id(db: aiosqlite.Connection, user_id: int) -> None:
    await db.execute(
        "DELETE FROM user_sessions WHERE user_id = ?",
        (user_id,),
    )
    await db.commit()


async def cleanup_expired_sessions(db: aiosqlite.Connection, expiry_days: int) -> int:
    cutoff = (datetime.now(UTC) - timedelta(days=expiry_days)).isoformat()
    cursor = await db.execute(
        "DELETE FROM user_sessions WHERE last_active < ?",
        (cutoff,),
    )
    await db.commit()
    return cursor.rowcount


# ---------------------------------------------------------------------------
# Relay group CRUD
# ---------------------------------------------------------------------------


async def get_relay_group(db: aiosqlite.Connection, user_token: str) -> dict | None:
    cursor = await db.execute("SELECT * FROM relay_groups WHERE user_token = ?", (user_token,))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def save_relay_group(db: aiosqlite.Connection, user_token: str, group_id: int) -> None:
    await db.execute(
        """INSERT INTO relay_groups (user_token, group_id, created_at)
           VALUES (?, ?, ?)
           ON CONFLICT(user_token) DO UPDATE SET group_id=excluded.group_id, created_at=excluded.created_at""",
        (user_token, group_id, _now()),
    )
    await db.commit()


async def delete_relay_group_record(db: aiosqlite.Connection, user_token: str) -> None:
    await db.execute("DELETE FROM relay_groups WHERE user_token = ?", (user_token,))
    await db.commit()


# ---------------------------------------------------------------------------
# Chat date cache helpers
# ---------------------------------------------------------------------------


async def get_cached_message_dates(
    db: aiosqlite.Connection,
    account: str,
    chat_id: int,
    year: int,
    month: int,
    max_age_hours: int = 1,
) -> list[str] | None:
    """Return cached dates or None if cache miss / stale."""
    cursor = await db.execute(
        "SELECT dates_json, cached_at FROM chat_date_cache WHERE account=? AND chat_id=? AND year=? AND month=?",
        (account, chat_id, year, month),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    now = datetime.now(UTC)
    is_current_month = year == now.year and month == now.month
    if is_current_month:
        cached_at = datetime.fromisoformat(row["cached_at"])
        if (now - cached_at) > timedelta(hours=max_age_hours):
            return None
    return json.loads(row["dates_json"])


async def set_cached_message_dates(
    db: aiosqlite.Connection,
    account: str,
    chat_id: int,
    year: int,
    month: int,
    dates: list[str],
) -> None:
    await db.execute(
        """INSERT INTO chat_date_cache (account, chat_id, year, month, dates_json, cached_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(account, chat_id, year, month) DO UPDATE SET
             dates_json=excluded.dates_json, cached_at=excluded.cached_at""",
        (account, chat_id, year, month, json.dumps(dates), _now()),
    )
    await db.commit()
