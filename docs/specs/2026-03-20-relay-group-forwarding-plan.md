# Relay Group Forwarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable automatic relay group forwarding when Account B cannot directly access the source chat, preserving "forwarded from" attribution without manual setup.

**Architecture:** Add relay group lifecycle management to `SessionManager`, insert `relay_forward` as a new mode between `forward` and `copy` in both `TransferEngine` and `LiveForwarder`, with batch cleanup piggyback on existing cooldown periods.

**Tech Stack:** Python 3.11+, Telethon (MTProto), FastAPI, aiosqlite, pytest

**Spec:** `docs/specs/2026-03-20-relay-group-forwarding-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `app/config.py` | Add `relay_forward_base_delay`, `live_relay_cleanup_threshold`, `relay_group_title` |
| Modify | `app/database.py` | Add `relay_groups` table DDL + CRUD functions |
| Modify | `app/rate_limiter.py:29-37` | Add `relay_forward` bucket to `_cfg()` |
| Modify | `app/telegram_client.py` | Add `ensure_relay_group()`, `delete_relay_group()`, `cleanup_relay_messages()` |
| Modify | `app/transfer_engine.py:57,184-202,315-320,429-501,624-629` | Add relay state, three-tier mode detection, relay_forward branch, file size filter, op type |
| Modify | `app/live_forwarder.py:57-108,121-177` | Add relay mode detection + relay_forward handler + cleanup |
| Modify | `app/models.py:131-142` | Add `mode` field to `TransferProgress` |
| Modify | `app/routes/user.py:46-55` | Add relay group cleanup to user data deletion + relay group API endpoints |
| Create | `tests/test_relay_group.py` | Unit tests for SessionManager relay methods |
| Create | `tests/test_relay_forward.py` | Unit tests for TransferEngine + LiveForwarder relay_forward mode |

**Note:** Line numbers reference the file state at plan start. Apply tasks in order; line numbers will drift after earlier modifications. API endpoints use path `/api/user/relay-group` (the `user.py` router has `prefix="/api/user"`). The `relay_groups` DB table is multi-user only — in single-user mode, relay group ID is cached in memory on SessionManager and not persisted.

---

### Task 1: Config — Add relay settings

**Files:**
- Modify: `app/config.py:81-86` (after `medium_account_multiplier`)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_config.py`, add:

```python
def test_relay_settings_defaults():
    from app.config import get_settings
    s = get_settings()
    assert s.relay_forward_base_delay == 4.0
    assert s.live_relay_cleanup_threshold == 10
    assert s.relay_group_title == "TMM Relay"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py::test_relay_settings_defaults -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'relay_forward_base_delay'`

- [ ] **Step 3: Write minimal implementation**

In `app/config.py`, add after line 81 (`medium_account_multiplier: float = 1.5`):

```python
    # Relay group forwarding
    relay_forward_base_delay: float = 4.0
    live_relay_cleanup_threshold: int = 10
    relay_group_title: str = "TMM Relay"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py::test_relay_settings_defaults -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "feat: add relay group config settings"
```

---

### Task 2: RateLimiter — Add relay_forward bucket

**Files:**
- Modify: `app/rate_limiter.py:29-37`
- Test: `tests/test_rate_limiter.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_rate_limiter.py`, add:

```python
def test_rate_limiter_relay_forward_config():
    from app.rate_limiter import RateLimiter

    rl = RateLimiter()
    cfg = rl._cfg("relay_forward")
    assert cfg.base_delay == 4.0
    assert cfg.jitter == 0.4
    assert cfg.burst == 1


def test_rate_limiter_relay_forward_rate():
    from app.rate_limiter import RateLimiter

    rl = RateLimiter()
    rate = rl._rate("relay_forward")
    assert abs(rate - 1.0 / 4.0) < 0.01
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_rate_limiter.py::test_rate_limiter_relay_forward_config tests/test_rate_limiter.py::test_rate_limiter_relay_forward_rate -v`
Expected: FAIL — `relay_forward` falls through to `forward` default (3.0 delay, not 4.0)

- [ ] **Step 3: Write minimal implementation**

In `app/rate_limiter.py`, modify `_cfg()` method (line 29-37). Add after the `"read"` entry:

```python
    def _cfg(self, op: str) -> _BucketConfig:
        s = get_settings()
        cfgs = {
            "forward": _BucketConfig(s.forward_base_delay, s.forward_jitter, s.forward_burst),
            "copy_text": _BucketConfig(s.copy_text_base_delay, s.copy_text_jitter, s.copy_text_burst),
            "copy_file": _BucketConfig(s.copy_file_base_delay, s.copy_file_jitter, s.copy_file_burst),
            "read": _BucketConfig(s.read_base_delay, s.read_jitter, s.read_burst),
            "relay_forward": _BucketConfig(s.relay_forward_base_delay, 0.4, 1),
        }
        return cfgs.get(op, cfgs["forward"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_rate_limiter.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/rate_limiter.py tests/test_rate_limiter.py
git commit -m "feat: add relay_forward bucket to RateLimiter"
```

---

### Task 3: Database — Add relay_groups table and CRUD

**Files:**
- Modify: `app/database.py`
- Create: `tests/test_relay_group.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_relay_group.py`:

```python
import pytest
import aiosqlite

from app.database import (
    get_relay_group,
    save_relay_group,
    delete_relay_group_record,
)


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_relay_group.py -v`
Expected: FAIL with `ImportError: cannot import name 'get_relay_group' from 'app.database'`

- [ ] **Step 3: Write minimal implementation**

In `app/database.py`, add the table DDL after `_CHAT_DATE_CACHE_TABLE` (line 68):

```python
_RELAY_GROUPS_TABLE = """
CREATE TABLE IF NOT EXISTS relay_groups (
    user_token TEXT PRIMARY KEY,
    group_id   INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
"""
```

In `init_db()` (line 95-98), add after multi-user tables:

```python
        else:
            await db.execute("PRAGMA secure_delete=ON")
            await db.executescript(_MULTI_USER_TABLES)
            await db.executescript(_RELAY_GROUPS_TABLE)
            await db.executescript(_CHAT_DATE_CACHE_TABLE)
```

Add CRUD functions at the end of the file (before the chat date cache section):

```python
# ---------------------------------------------------------------------------
# Relay group CRUD
# ---------------------------------------------------------------------------


async def get_relay_group(db: aiosqlite.Connection, user_token: str) -> dict | None:
    cursor = await db.execute(
        "SELECT * FROM relay_groups WHERE user_token = ?", (user_token,)
    )
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_relay_group.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/database.py tests/test_relay_group.py
git commit -m "feat: add relay_groups table and CRUD functions"
```

---

### Task 4: SessionManager — Add relay group lifecycle methods

**Files:**
- Modify: `app/telegram_client.py`
- Modify: `tests/test_relay_group.py` (add SessionManager tests)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_relay_group.py`:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.telegram_client import SessionManager


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

    # Mock Account A: create channel, export invite
    mock_result = MagicMock()
    mock_result.chats = [MagicMock(id=123456)]
    sm._clients["account_a"].__call__ = AsyncMock(side_effect=[
        mock_result,  # CreateChannelRequest
        MagicMock(link="https://t.me/+abc123"),  # ExportChatInviteRequest
    ])
    sm._clients["account_a"].get_entity = AsyncMock(return_value=mock_entity_a)

    # Mock Account B: join via invite, get_entity
    sm._clients["account_b"].__call__ = AsyncMock()  # ImportChatInviteRequest
    sm._clients["account_b"].get_entity = AsyncMock(return_value=mock_entity_b)

    relay_a, relay_b = await sm.ensure_relay_group()
    assert relay_a is mock_entity_a
    assert relay_b is mock_entity_b

    # Second call returns cached
    relay_a2, relay_b2 = await sm.ensure_relay_group()
    assert relay_a2 is mock_entity_a  # same objects, no new API calls


@pytest.mark.asyncio
async def test_ensure_relay_group_idempotent_with_lock():
    sm = _make_session_manager()
    sm._relay_entity_a = MagicMock()
    sm._relay_entity_b = MagicMock()
    sm._relay_group_id = 999

    # Already cached — should return immediately
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
    sm._clients["account_a"].__call__ = AsyncMock(side_effect=[
        mock_result,
        MagicMock(link="https://t.me/+abc123"),
    ])
    sm._clients["account_a"].get_entity = AsyncMock(return_value=mock_entity_a)
    sm._clients["account_b"].__call__ = AsyncMock()
    sm._clients["account_b"].get_entity = AsyncMock(return_value=mock_entity_b)

    await sm.ensure_relay_group(db=db, user_token="token123")

    # Verify persisted to DB
    result = await get_relay_group(db, "token123")
    assert result is not None
    assert result["group_id"] == 123456


@pytest.mark.asyncio
async def test_cleanup_relay_messages_best_effort():
    sm = _make_session_manager()
    sm._relay_group_id = 123456
    sm._relay_entity_a = MagicMock()

    # cleanup should not raise even if the API call fails
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_relay_group.py::test_ensure_relay_group_creates_and_caches -v`
Expected: FAIL with `AttributeError: 'SessionManager' object has no attribute 'ensure_relay_group'`

- [ ] **Step 3: Write minimal implementation**

In `app/telegram_client.py`, add imports at top:

```python
import asyncio
from pathlib import Path
from typing import Literal

from telethon import TelegramClient
from telethon.sessions import SQLiteSession
```

Add new state to `SessionManager.__init__()` (after line 25):

```python
        self._relay_group_id: int | None = None
        self._relay_entity_a = None
        self._relay_entity_b = None
        self._relay_lock = asyncio.Lock()
```

Add methods at the end of the `SessionManager` class (after `disconnect_all`):

```python
    async def ensure_relay_group(self, db=None, user_token: str | None = None):
        """Return (relay_entity_a, relay_entity_b), creating the group if needed.

        Idempotent and protected by asyncio.Lock to prevent concurrent creation.
        """
        async with self._relay_lock:
            # 1. Already cached
            if self._relay_entity_a and self._relay_entity_b:
                return self._relay_entity_a, self._relay_entity_b

            source = self._clients.get("account_a")
            dest = self._clients.get("account_b")
            if not source or not dest:
                raise RuntimeError("Both accounts must be connected")

            # 2. Try loading from DB
            if db and user_token and self._relay_group_id is None:
                from .database import get_relay_group

                record = await get_relay_group(db, user_token)
                if record:
                    self._relay_group_id = record["group_id"]

            # 3. Verify existing group is accessible
            if self._relay_group_id:
                try:
                    self._relay_entity_a = await source.get_entity(self._relay_group_id)
                    self._relay_entity_b = await dest.get_entity(self._relay_group_id)
                    return self._relay_entity_a, self._relay_entity_b
                except Exception:
                    # Group no longer accessible, clear and recreate
                    self._relay_group_id = None
                    self._relay_entity_a = None
                    self._relay_entity_b = None
                    if db and user_token:
                        from .database import delete_relay_group_record

                        await delete_relay_group_record(db, user_token)

            # 4. Create new supergroup
            from telethon.tl.functions.channels import CreateChannelRequest
            from telethon.tl.functions.messages import ExportChatInviteRequest, ImportChatInviteRequest

            from .config import get_settings

            s = get_settings()
            result = await source(CreateChannelRequest(
                title=s.relay_group_title, about="", megagroup=True,
            ))
            group_id = result.chats[0].id
            self._relay_group_id = group_id

            # 5. Generate invite link
            entity_a = await source.get_entity(group_id)
            invite = await source(ExportChatInviteRequest(entity_a))

            # 6. Account B joins via invite link
            invite_hash = invite.link.split("/")[-1]
            if invite_hash.startswith("+"):
                invite_hash = invite_hash[1:]
            try:
                await dest(ImportChatInviteRequest(invite_hash))
            except Exception:
                # Retry with fresh invite
                invite = await source(ExportChatInviteRequest(entity_a))
                invite_hash = invite.link.split("/")[-1]
                if invite_hash.startswith("+"):
                    invite_hash = invite_hash[1:]
                await dest(ImportChatInviteRequest(invite_hash))

            self._relay_entity_a = entity_a
            self._relay_entity_b = await dest.get_entity(group_id)

            # 7. Persist
            if db and user_token:
                from .database import save_relay_group

                await save_relay_group(db, user_token, group_id)

            return self._relay_entity_a, self._relay_entity_b

    async def delete_relay_group(self, db=None, user_token: str | None = None) -> None:
        """Delete the relay group from Telegram and clear all state."""
        if self._relay_group_id and self._relay_entity_a:
            try:
                from telethon.tl.functions.channels import DeleteChannelRequest

                source = self._clients.get("account_a")
                if source:
                    await source(DeleteChannelRequest(self._relay_entity_a))
            except Exception:
                pass  # best effort

        self._relay_group_id = None
        self._relay_entity_a = None
        self._relay_entity_b = None

        if db and user_token:
            from .database import delete_relay_group_record

            await delete_relay_group_record(db, user_token)

    async def cleanup_relay_messages(self, message_ids: list[int]) -> None:
        """Best-effort batch delete messages from the relay group."""
        if not message_ids or not self._relay_entity_a:
            return
        try:
            from telethon.tl.functions.channels import DeleteMessagesRequest

            source = self._clients.get("account_a")
            if source:
                await source(DeleteMessagesRequest(self._relay_entity_a, message_ids))
        except Exception as e:
            import logging

            logging.getLogger(__name__).debug("Relay cleanup failed: %s", e)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_relay_group.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/telegram_client.py tests/test_relay_group.py
git commit -m "feat: add relay group lifecycle to SessionManager"
```

---

### Task 5: Models — Add mode field to TransferProgress

**Files:**
- Modify: `app/models.py:131-142`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_models.py`, add:

```python
def test_transfer_progress_mode_field():
    from app.models import TransferProgress

    p = TransferProgress()
    assert p.mode is None

    p2 = TransferProgress(mode="relay_forward")
    assert p2.mode == "relay_forward"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models.py::test_transfer_progress_mode_field -v`
Expected: FAIL — `mode` not a valid field

- [ ] **Step 3: Write minimal implementation**

In `app/models.py`, add to `TransferProgress` class (after line 142, `rate_limit_wait_seconds`):

```python
    mode: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_models.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add app/models.py tests/test_models.py
git commit -m "feat: add mode field to TransferProgress"
```

---

### Task 6: TransferEngine — Three-tier mode detection + relay_forward

**Files:**
- Modify: `app/transfer_engine.py`
- Create: `tests/test_relay_forward.py`

This is the largest task. It modifies: mode detection in `_run_inner()`, the `_transfer_message()` method, the `_get_op_type()` method, the file size filter, batch cleanup integration, and final cleanup.

**Important:** `source_client` is already passed as a parameter to `_transfer_message()` — use it directly, don't re-fetch from session_manager. `source_entity_a` should be resolved once in `_run_inner()` and stored on `self` to avoid repeated get_entity calls inside the retry loop.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_relay_forward.py`:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.config as config_module
from app.config import init_settings
from app.models import TransferJobCreate, TransferMode
from app.transfer_engine import TransferEngine


@pytest.fixture(autouse=True)
def _setup_settings(monkeypatch):
    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "abc123")
    config_module._settings = None
    init_settings()


def test_engine_has_relay_state():
    engine = TransferEngine(session_manager=MagicMock(), persist_checkpoints=False)
    assert engine._relay_a is None
    assert engine._relay_b is None
    assert engine._pending_relay_ids == []
    assert engine._source_entity_a is None


def test_get_op_type_relay_forward():
    engine = TransferEngine(session_manager=MagicMock(), persist_checkpoints=False)
    engine._effective_mode = "relay_forward"
    msg = MagicMock(media=None)
    assert engine._get_op_type(msg) == "relay_forward"

    msg_with_media = MagicMock(media=MagicMock())
    assert engine._get_op_type(msg_with_media) == "relay_forward"


def test_get_op_type_forward_and_copy():
    engine = TransferEngine(session_manager=MagicMock(), persist_checkpoints=False)
    engine._effective_mode = "forward"
    assert engine._get_op_type(MagicMock(media=None)) == "forward"

    engine._effective_mode = "copy"
    assert engine._get_op_type(MagicMock(media=MagicMock())) == "copy_file"
    assert engine._get_op_type(MagicMock(media=None)) == "copy_text"


@pytest.mark.asyncio
async def test_transfer_message_relay_forward_branch():
    """relay_forward should forward via relay: source→relay, then relay→dest."""
    mock_sm = MagicMock()
    engine = TransferEngine(session_manager=mock_sm, persist_checkpoints=False)
    engine._effective_mode = "relay_forward"
    engine._relay_a = MagicMock()
    engine._relay_b = MagicMock()
    engine._source_entity_a = MagicMock()
    engine.config = MagicMock(source_chat_id=111)

    source_client = AsyncMock()
    dest_client = AsyncMock()
    msg = MagicMock(id=42)

    relay_msg = MagicMock(id=99)
    source_client.forward_messages = AsyncMock(return_value=[relay_msg])
    dest_client.forward_messages = AsyncMock()

    result = await engine._transfer_message(
        None, source_client, dest_client, MagicMock(), None, msg, "relay_forward"
    )
    assert result == "done"
    source_client.forward_messages.assert_awaited_once()
    dest_client.forward_messages.assert_awaited_once()
    assert 99 in engine._pending_relay_ids


@pytest.mark.asyncio
async def test_relay_forward_downgrades_on_forwards_restricted():
    """ChatForwardsRestrictedError should downgrade to copy and retry."""
    from telethon import errors as tg_errors

    mock_sm = MagicMock()
    engine = TransferEngine(session_manager=mock_sm, persist_checkpoints=False)
    engine._effective_mode = "relay_forward"
    engine._relay_a = MagicMock()
    engine._relay_b = MagicMock()
    engine._source_entity_a = MagicMock()
    engine.config = MagicMock(source_chat_id=111)
    engine.progress = MagicMock(mode="relay_forward")

    source_client = AsyncMock()
    dest_client = AsyncMock()
    msg = MagicMock(id=42, text="hello", media=None, entities=None)

    source_client.forward_messages = AsyncMock(
        side_effect=tg_errors.ChatForwardsRestrictedError(request=None)
    )
    dest_client.send_message = AsyncMock()

    result = await engine._transfer_message(
        None, source_client, dest_client, MagicMock(), None, msg, "relay_forward"
    )
    assert engine._effective_mode == "copy"
    assert engine.progress.mode == "copy"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_relay_forward.py -v`
Expected: FAIL — `_relay_a` not an attribute, `_get_op_type` returns `"copy_file"` for relay_forward

- [ ] **Step 3: Write implementation — instance state and _get_op_type**

In `app/transfer_engine.py`, add to `__init__()` after line 57 (`self._effective_mode`):

```python
        self._relay_a = None
        self._relay_b = None
        self._pending_relay_ids: list[int] = []
        self._source_entity_a = None  # resolved once in _run_inner, reused in _transfer_message
```

Modify `_get_op_type()` (line 624-629):

```python
    def _get_op_type(self, msg) -> str:
        if self._effective_mode == "forward":
            return "forward"
        if self._effective_mode == "relay_forward":
            return "relay_forward"
        if msg.media:
            return "copy_file"
        return "copy_text"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_relay_forward.py -v`
Expected: PASS

- [ ] **Step 5: Implement three-tier mode detection in `_run_inner()`**

Replace lines 194-202 (the existing two-tier detection) with:

```python
            if is_private and self._effective_mode == "forward":
                logger.warning("Source is a private chat, falling back to copy mode")
                self._effective_mode = "copy"
            elif self._effective_mode == "forward":
                try:
                    source_entity_b = await dest_client.get_entity(cfg.source_chat_id)
                except Exception:
                    # Account B can't access source — try relay group
                    try:
                        self._relay_a, self._relay_b = await self._session_manager.ensure_relay_group()
                        self._effective_mode = "relay_forward"
                        logger.info("Using relay group for forwarding")
                    except Exception:
                        logger.warning("Relay group unavailable, falling back to copy mode")
                        self._effective_mode = "copy"

            # Store source_entity_a for reuse in _transfer_message relay_forward branch
            self._source_entity_a = source_entity_a  # resolved above (line ~187)
```

Set mode on progress object (after mode detection, before message collection):

```python
            self.progress.mode = self._effective_mode
```

- [ ] **Step 6: Implement relay_forward branch in `_transfer_message()`**

Replace lines 443-446 in `_transfer_message()`:

Note: `source_client` is already a parameter of `_transfer_message()` — use it directly. `self._source_entity_a` was resolved once in `_run_inner()`.

```python
                if mode == "forward":
                    await dest_client.forward_messages(dest_entity, msg.id, source_entity_b)
                elif mode == "relay_forward":
                    # Step 1: Account A forward source → relay (uses source_client param)
                    relay_msgs = await source_client.forward_messages(
                        self._relay_a, msg.id, self._source_entity_a
                    )
                    relay_msg_id = relay_msgs[0].id
                    self._pending_relay_ids.append(relay_msg_id)
                    # Step 2: Account B forward relay → destination
                    await dest_client.forward_messages(dest_entity, relay_msg_id, self._relay_b)
                else:
                    await self._copy_message(dest_client, dest_entity, msg)
```

Add ChatForwardsRestrictedError interception before `classify()` (around line 453):

```python
            except Exception as exc:
                # Intercept ChatForwardsRestrictedError in relay_forward mode —
                # source chat forbids forwarding, downgrade entire job to copy
                if mode == "relay_forward" and isinstance(exc, tg_errors.ChatForwardsRestrictedError):
                    logger.warning("Source chat forbids forwarding, downgrading to copy mode")
                    self._effective_mode = "copy"
                    self.progress.mode = "copy"  # update SSE-visible mode
                    # Retry this message in copy mode
                    return await self._transfer_message(
                        db, source_client, dest_client, dest_entity, source_entity_b, msg, "copy"
                    )

                strategy, reason = classify(exc)
```

- [ ] **Step 7: Add file size filter skip for relay_forward**

Modify line 315-320 (file size filter):

```python
                # File size filter (copy mode only — forward/relay_forward don't re-upload)
                if self._effective_mode == "copy" and cfg.max_file_size_mb and has_media and msg.file:
                    size_mb = (msg.file.size or 0) / (1024 * 1024)
                    if size_mb > cfg.max_file_size_mb:
                        _skip()
                        continue
```

- [ ] **Step 8: Add relay cleanup piggyback on batch_cooldown**

After line 385 (`await self.rate_limiter.batch_cooldown()`), add:

```python
                # Relay cleanup during batch cooldown
                if self._pending_relay_ids and self.rate_limiter._batch_counter % get_settings().batch_size == 0:
                    await self._session_manager.cleanup_relay_messages(self._pending_relay_ids)
                    self._pending_relay_ids.clear()
```

- [ ] **Step 9: Add final relay cleanup**

In the `finally` block (after line 426), before `if db:`, add:

```python
            # Final relay cleanup
            if self._pending_relay_ids and self._session_manager:
                try:
                    await self._session_manager.cleanup_relay_messages(self._pending_relay_ids)
                    self._pending_relay_ids.clear()
                except Exception:
                    pass
```

- [ ] **Step 10: Update _transfer_message call to pass mode**

The call at line 351-353 already passes `self._effective_mode` — no change needed. But confirm `source_client` is passed through correctly for relay_forward branch access. The branch accesses `self._session_manager` directly, so no signature change required.

- [ ] **Step 11: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 12: Commit**

```bash
git add app/transfer_engine.py tests/test_relay_forward.py
git commit -m "feat: add relay_forward mode to TransferEngine"
```

---

### Task 7: LiveForwarder — Add relay_forward mode

**Files:**
- Modify: `app/live_forwarder.py`
- Modify: `tests/test_relay_forward.py` (add LiveForwarder tests)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_relay_forward.py`:

```python
from app.live_forwarder import LiveForwarder


def test_live_forwarder_has_relay_state():
    lf = LiveForwarder(session_manager=MagicMock())
    assert lf._relay_a is None
    assert lf._relay_b is None
    assert lf._pending_relay_ids == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_relay_forward.py::test_live_forwarder_has_relay_state -v`
Expected: FAIL — `_relay_a` not an attribute

- [ ] **Step 3: Write implementation — state + mode detection + handler**

In `app/live_forwarder.py`, add new instance state in `__init__()` (after line 34):

```python
        self._relay_a = None
        self._relay_b = None
        self._pending_relay_ids: list[int] = []
```

Modify `start()` method — replace lines 90-98 (the mode detection block).

**Note:** This adds a new `source_client.get_entity()` call for the private chat check (uses Account A). The existing `dest_client.get_entity()` (Account B) call is preserved for forward mode. These are two separate calls on different clients.

```python
        # Resolve source for Account B (forward mode needs it)
        self.source_entity_b = None
        effective_mode = mode

        # Check if source is a private chat (Account A's perspective)
        try:
            source_entity = await source_client.get_entity(source_chat_id)
            from telethon.tl.types import User
            is_private = isinstance(source_entity, User)
        except Exception:
            is_private = True

        if is_private and mode == "forward":
            effective_mode = "copy"
        elif mode == "forward":
            try:
                # Account B must also see the source for direct forward
                self.source_entity_b = await dest_client.get_entity(source_chat_id)
            except Exception:
                # Try relay group
                try:
                    self._relay_a, self._relay_b = await self._session_manager.ensure_relay_group()
                    effective_mode = "relay_forward"
                    logger.info("Live forwarder using relay group")
                except Exception:
                    logger.warning("Relay unavailable, falling back to copy")
                    effective_mode = "copy"
        self.mode = effective_mode
```

Modify `_handle_message()` — update rate limit op type (line 150):

```python
        op = "relay_forward" if self.mode == "relay_forward" else (
            "forward" if self.mode == "forward" else ("copy_file" if has_media else "copy_text")
        )
```

Add relay_forward branch in the transfer section (replace lines 154-159):

```python
        try:
            if self.mode == "forward":
                await dest_client.forward_messages(self.dest_entity, msg.id, self.source_entity_b)
            elif self.mode == "relay_forward":
                source_client = self._session_manager.get_client("account_a")
                source_entity_a = await source_client.get_entity(self.source_chat_id)
                relay_msgs = await source_client.forward_messages(
                    self._relay_a, msg.id, source_entity_a
                )
                relay_msg_id = relay_msgs[0].id
                self._pending_relay_ids.append(relay_msg_id)
                await dest_client.forward_messages(self.dest_entity, relay_msg_id, self._relay_b)
                # Threshold cleanup
                if len(self._pending_relay_ids) >= get_settings().live_relay_cleanup_threshold:
                    await self._session_manager.cleanup_relay_messages(self._pending_relay_ids)
                    self._pending_relay_ids.clear()
            else:
                await self._copy_message(dest_client, msg)
```

Add ChatForwardsRestrictedError interception in error handler (after line 162):

```python
            # Intercept forwards-restricted in relay mode — downgrade to copy
            if self.mode == "relay_forward" and isinstance(exc, tg_errors.ChatForwardsRestrictedError):
                logger.warning("Source forbids forwarding, downgrading live forwarder to copy")
                self.mode = "copy"
                # Retry this message in copy mode
                try:
                    await self._copy_message(dest_client, msg)
                    self.stats["forwarded"] += 1
                    self._notify("live_message", {"message_id": msg.id, "status": "done"})
                    return
                except Exception as copy_exc:
                    exc = copy_exc  # fall through to normal error handling
```

Add final cleanup in `stop()` (after line 117, before setting `self.active = False`):

```python
        # Final relay cleanup
        if self._pending_relay_ids and self._session_manager:
            try:
                await self._session_manager.cleanup_relay_messages(self._pending_relay_ids)
                self._pending_relay_ids.clear()
            except Exception:
                pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_relay_forward.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add app/live_forwarder.py tests/test_relay_forward.py
git commit -m "feat: add relay_forward mode to LiveForwarder"
```

---

### Task 8: User data deletion — Clean up relay group

**Files:**
- Modify: `app/routes/user.py:46-55`
- Test: `tests/test_routes_user.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_routes_user.py` (or verify existing delete test covers relay cleanup — depends on existing test structure). The key change is a single line, so a focused integration test:

Extend the existing test pattern in `tests/test_routes_user.py`. The key assertion is that `delete_relay_group` is called during the user data deletion flow. If the existing tests use a mock `session_manager`, add `delete_relay_group = AsyncMock()` to the mock and assert it was awaited:

```python
# In the existing delete user data test setup, add to the mock session_manager:
mock_sm.delete_relay_group = AsyncMock()

# After calling the delete endpoint, assert:
mock_sm.delete_relay_group.assert_awaited_once()
```

If no existing test calls the delete endpoint with a full mock context, write a standalone test:

```python
@pytest.mark.asyncio
async def test_delete_user_data_calls_relay_group_cleanup():
    """Verify route calls delete_relay_group during teardown."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.routes.user import delete_user_data

    mock_sm = MagicMock()
    mock_sm.delete_relay_group = AsyncMock()
    mock_sm.is_authorized = AsyncMock(return_value=False)
    mock_sm.disconnect_all = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.session_manager = mock_sm
    mock_ctx.engine = None
    mock_ctx.live_forwarder = None

    mock_request = MagicMock()
    mock_request.cookies = {"session_id": "test_token"}

    with patch("app.routes.user.get_context", return_value=mock_ctx), \
         patch("app.routes.user.get_db") as mock_get_db, \
         patch("app.routes.user.remove_context"), \
         patch("app.routes.user.get_settings") as mock_gs:
        mock_gs.return_value = MagicMock(single_user_mode=False)
        mock_db = AsyncMock()
        mock_get_db.return_value = mock_db

        await delete_user_data(mock_request)
        mock_sm.delete_relay_group.assert_awaited_once()
```

- [ ] **Step 2: Write implementation**

In `app/routes/user.py`, add relay group cleanup between Step 2 (stop forwarder) and Step 3 (logout):

```python
    # Step 2.5: Delete relay group
    if ctx.session_manager and hasattr(ctx.session_manager, "delete_relay_group"):
        try:
            await ctx.session_manager.delete_relay_group()
        except Exception:
            pass  # best effort
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_routes_user.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add app/routes/user.py tests/test_routes_user.py
git commit -m "feat: clean up relay group during user data deletion"
```

---

### Task 9: API endpoints — Relay group status and management

**Files:**
- Modify: `app/routes/user.py`

- [ ] **Step 1: Add GET /api/relay-group endpoint**

```python
@router.get("/relay-group")
async def get_relay_group_status(request: Request):
    """Return relay group status for current user."""
    s = get_settings()
    if s.single_user_mode:
        raise HTTPException(status_code=404, detail="Not available in single-user mode")

    token = request.cookies.get("session_id")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    ctx = get_context(token)
    if not ctx:
        raise HTTPException(status_code=401, detail="Session expired")

    if ctx.session_manager and ctx.session_manager._relay_group_id:
        db = await get_db()
        try:
            from ..database import get_relay_group as get_relay_group_record
            record = await get_relay_group_record(db, hash_token(token))
        finally:
            await db.close()

        return {
            "exists": True,
            "group_id": ctx.session_manager._relay_group_id,
            "created_at": record["created_at"] if record else None,
        }

    return {"exists": False, "group_id": None, "created_at": None}
```

- [ ] **Step 2: Add DELETE /api/relay-group endpoint**

```python
@router.delete("/relay-group")
async def delete_relay_group_endpoint(request: Request):
    """Delete the relay group entirely."""
    s = get_settings()
    if s.single_user_mode:
        raise HTTPException(status_code=404, detail="Not available in single-user mode")

    token = request.cookies.get("session_id")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    ctx = get_context(token)
    if not ctx:
        raise HTTPException(status_code=401, detail="Session expired")

    if not ctx.session_manager or not ctx.session_manager._relay_group_id:
        raise HTTPException(status_code=404, detail="No relay group exists")

    db = await get_db()
    try:
        await ctx.session_manager.delete_relay_group(db=db, user_token=hash_token(token))
    finally:
        await db.close()

    return {"status": "deleted"}
```

- [ ] **Step 3: Add DELETE /api/relay-group/messages endpoint**

```python
@router.delete("/relay-group/messages")
async def clear_relay_group_messages(request: Request):
    """Delete all messages in the relay group (capped at 1000)."""
    s = get_settings()
    if s.single_user_mode:
        raise HTTPException(status_code=404, detail="Not available in single-user mode")

    token = request.cookies.get("session_id")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    ctx = get_context(token)
    if not ctx:
        raise HTTPException(status_code=401, detail="Session expired")

    sm = ctx.session_manager
    if not sm or not sm._relay_group_id or not sm._relay_entity_a:
        raise HTTPException(status_code=404, detail="No relay group exists")

    source = sm._clients.get("account_a")
    if not source:
        raise HTTPException(status_code=500, detail="Account A not connected")

    deleted = 0
    batch = []
    async for msg in source.iter_messages(sm._relay_entity_a, limit=1000):
        batch.append(msg.id)
        if len(batch) >= 100:
            await sm.cleanup_relay_messages(batch)
            deleted += len(batch)
            batch.clear()
    if batch:
        await sm.cleanup_relay_messages(batch)
        deleted += len(batch)

    return {"status": "cleared", "deleted": deleted}
```

- [ ] **Step 4: Write route tests**

Add to `tests/test_routes_user.py` (or a new `tests/test_routes_relay.py`):

```python
@pytest.mark.asyncio
async def test_get_relay_group_status_no_group():
    """GET /api/user/relay-group returns exists=False when no relay group."""
    from unittest.mock import MagicMock, patch
    from app.routes.user import get_relay_group_status

    mock_sm = MagicMock()
    mock_sm._relay_group_id = None
    mock_ctx = MagicMock(session_manager=mock_sm)
    mock_request = MagicMock()
    mock_request.cookies = {"session_id": "test"}

    with patch("app.routes.user.get_context", return_value=mock_ctx), \
         patch("app.routes.user.get_settings") as mock_gs:
        mock_gs.return_value = MagicMock(single_user_mode=False)
        result = await get_relay_group_status(mock_request)
        assert result["exists"] is False


@pytest.mark.asyncio
async def test_delete_relay_group_404_when_none():
    """DELETE /api/user/relay-group returns 404 when no relay group exists."""
    from unittest.mock import MagicMock, patch
    from fastapi import HTTPException
    from app.routes.user import delete_relay_group_endpoint

    mock_sm = MagicMock()
    mock_sm._relay_group_id = None
    mock_ctx = MagicMock(session_manager=mock_sm)
    mock_request = MagicMock()
    mock_request.cookies = {"session_id": "test"}

    with patch("app.routes.user.get_context", return_value=mock_ctx), \
         patch("app.routes.user.get_settings") as mock_gs:
        mock_gs.return_value = MagicMock(single_user_mode=False)
        with pytest.raises(HTTPException) as exc_info:
            await delete_relay_group_endpoint(mock_request)
        assert exc_info.value.status_code == 404
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add app/routes/user.py tests/
git commit -m "feat: add relay group API endpoints (GET, DELETE, clear messages)"
```

---

### Task 10: Final integration test + cleanup

**Files:**
- All modified files
- Test: `tests/test_relay_forward.py`

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 2: Run linter**

Run: `ruff check app/ tests/`
Expected: No errors

- [ ] **Step 3: Run formatter**

Run: `ruff format app/ tests/`

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: lint and format relay group feature"
```

- [ ] **Step 5: Verify all commits on branch**

Run: `git log --oneline main..HEAD`
Expected: All relay group commits listed
