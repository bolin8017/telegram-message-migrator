# Relay Group Forwarding Design

**Date**: 2026-03-20
**Status**: Approved
**Scope**: TransferEngine (batch) + LiveForwarder (real-time)

## Problem

Telegram's `forward_messages(dest, msg_id, from_peer)` requires the calling client to have read access to `from_peer`. When Account B (destination) cannot access Account A's source chat — which is the common case for private chats and chats where Account B is not a member — the forward mode silently falls back to copy mode. Copy mode works but is slower (re-uploads media) and loses the "forwarded from" attribution.

## Solution

Introduce an automated relay group mechanism. Account A creates a private supergroup, invites Account B via invite link, and uses it as an intermediary: A forwards source → relay, B forwards relay → destination. The relay group is created on-demand, persisted for reuse, and cleaned up during batch cooldowns.

## Forwarding Strategy (Two-Layer Fallback)

```
For each transfer job (decided once at start, not per-message):

1. Account B tries get_entity(source_chat_id)
   ├─ Success → "forward" mode (B forwards directly)
   └─ Failure ↓
2. session_manager.ensure_relay_group()
   ├─ Success → "relay_forward" mode (A→relay→B→destination)
   └─ Failure ↓
3. "copy" mode (download + re-upload)
```

### Key rules

- **Probe once**: Mode is determined at transfer start, not per-message.
- **No upgrade after downgrade**: If relay_forward fails mid-transfer, the job switches to copy mode permanently. This downgrade is stored in `TransferEngine._effective_mode` (in-memory only). On resume after restart, mode is re-probed from scratch — if the relay group still exists, relay_forward will be re-selected. This is intentional: a transient failure (e.g., FloodWait) should not permanently prevent relay use.
- **Private chats skip to copy**: If source is a `User` entity (private chat), skip directly to copy mode. This check applies to both TransferEngine and LiveForwarder.
- **File size filter**: `relay_forward` mode skips the file size filter, same as `forward` mode — no re-upload occurs.

## SessionManager Changes

### New state

```python
_relay_group_id: int | None = None
_relay_entity_a: Entity | None = None  # Account A's view of relay group
_relay_entity_b: Entity | None = None  # Account B's view of relay group
_relay_lock: asyncio.Lock              # Prevents concurrent creation races
```

### New methods

#### `ensure_relay_group() -> tuple[Entity, Entity]`

Idempotent, protected by `_relay_lock`. Returns `(relay_entity_a, relay_entity_b)`.

1. Acquire `_relay_lock`.
2. If cached in memory → return immediately.
3. If relay group ID exists in DB → verify both accounts can access it via `get_entity()` → cache and return.
   - If verification fails (group deleted externally) → clear DB record, proceed to step 4.
4. Account A creates supergroup via `CreateChannelRequest(title="TMM Relay", about="", megagroup=True)`.
5. Account A generates invite link via `ExportChatInviteRequest`.
6. Account B joins via `ImportChatInviteRequest` (bypasses privacy settings).
7. Store relay group ID in DB (per-user).
8. Cache and return.

The `asyncio.Lock` prevents races when TransferEngine and LiveForwarder call `ensure_relay_group()` concurrently for the same user.

#### `delete_relay_group() -> None`

User-initiated. Account A deletes the group via `DeleteChannelRequest` → clears DB record → clears cache. Only the group creator (Account A) can delete a supergroup.

#### `cleanup_relay_messages(message_ids: list[int]) -> None`

Best-effort batch delete via `DeleteMessagesRequest`, executed by **Account A** (group creator/admin). Failures are logged but do not raise.

### Why supergroup (`megagroup=True`)

- Supports `DeleteMessagesRequest` for batch message deletion.
- Invite links are permanent by default.
- No functional downside vs. basic group for this use case.

## Database Changes

New table for relay group persistence (per-user). Added to `_MULTI_USER_TABLES` in `database.py` `init_db()`:

```sql
CREATE TABLE IF NOT EXISTS relay_groups (
    user_token TEXT PRIMARY KEY,
    group_id   INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
```

This table is multi-user only. In single-user mode, relay group ID is cached in memory on `SessionManager` and not persisted (single-user sessions don't survive restarts anyway).

## TransferEngine Changes

### New instance state

```python
self._relay_a: Entity | None = None       # Set during mode detection
self._relay_b: Entity | None = None
self._pending_relay_ids: list[int] = []   # Accumulates relay msg IDs for cleanup
```

### Mode detection

In `_run_inner()`, replace the existing two-tier detection (forward → copy) with three tiers:

```python
if is_private and mode == "forward":
    effective_mode = "copy"
elif mode == "forward":
    try:
        source_entity_b = await dest_client.get_entity(source_chat_id)
        effective_mode = "forward"
    except Exception:
        try:
            self._relay_a, self._relay_b = await session_manager.ensure_relay_group()
            effective_mode = "relay_forward"
        except Exception:
            effective_mode = "copy"
```

### relay_forward in `_transfer_message()`

The relay_forward logic goes **inside `_transfer_message()`** as a new branch, alongside the existing `forward` and `copy` branches. This ensures relay_forward benefits from the same retry/error-handling/checkpoint logic.

`_transfer_message()` accesses relay state via `self._relay_a`, `self._relay_b`, and `self._pending_relay_ids` (instance attributes set during mode detection).

```python
if self._effective_mode == "relay_forward":
    # Step 1: Account A forward source → relay
    relay_msgs = await source_client.forward_messages(
        self._relay_a, msg.id, source_entity_a
    )
    relay_msg_id = relay_msgs[0].id
    self._pending_relay_ids.append(relay_msg_id)

    # Step 2: Account B forward relay → destination
    await dest_client.forward_messages(dest_entity, relay_msg_id, self._relay_b)
```

**Error interception**: Before delegating to `error_strategies.classify()`, `_transfer_message()` checks: if mode is `relay_forward` and error is `ChatForwardsRestrictedError`, downgrade `self._effective_mode` to `"copy"` and retry the current message in copy mode. This is handled in `_transfer_message()` itself, not by changing `error_strategies.py`.

### Batch cleanup during cooldown

Piggyback on the existing batch cooldown (every `batch_size` messages):

```python
if count % batch_size == 0:
    if self._pending_relay_ids:
        await session_manager.cleanup_relay_messages(self._pending_relay_ids)
        self._pending_relay_ids.clear()
    await asyncio.sleep(cooldown_sec)
```

Final cleanup runs at transfer end (success, cancel, or failure).

### Rate limiting

Add `"relay_forward"` operation type to `RateLimiter._cfg()`:

```python
"relay_forward": BucketConfig(
    base_delay=settings.relay_forward_base_delay,  # 4.0s
    jitter=0.4,
    burst=1,
),
```

Update `TransferEngine._get_op_type()` to return `"relay_forward"` when `self._effective_mode == "relay_forward"`.

## LiveForwarder Changes

### Mode detection

Same three-tier logic in `start()`, including private chat check:

```python
# Check if source is private chat
try:
    source_entity = await source_client.get_entity(source_chat_id)
    is_private = isinstance(source_entity, User)
except Exception:
    is_private = True

if is_private:
    self.mode = "copy"
elif mode == "forward":
    try:
        self.source_entity_b = await dest_client.get_entity(source_chat_id)
        self.mode = "forward"
    except Exception:
        try:
            self.relay_a, self.relay_b = await session_manager.ensure_relay_group()
            self.mode = "relay_forward"
        except Exception:
            self.mode = "copy"
```

### relay_forward in event handler

Same A→relay→B→destination logic as TransferEngine.

### Cleanup strategy

Accumulate relay message IDs, clean up every 10 messages:

```python
self._pending_relay_ids: list[int] = []

self._pending_relay_ids.append(relay_msg_id)
if len(self._pending_relay_ids) >= settings.live_relay_cleanup_threshold:
    await session_manager.cleanup_relay_messages(self._pending_relay_ids)
    self._pending_relay_ids.clear()
```

Final cleanup on `stop()`.

## API Endpoints

Added to existing routes (per-user resource, in `routes/user.py`):

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/user/relay-group` | Relay group status (exists?, group ID, created_at) |
| `DELETE` | `/api/user/relay-group` | Delete the relay group entirely (via `DeleteChannelRequest`) |
| `DELETE` | `/api/user/relay-group/messages` | Delete all messages currently in the relay group. Iterates messages via `get_messages()` and deletes in batches of 100 via `DeleteMessagesRequest`. Capped at 1000 messages per call to avoid rate limits; returns count deleted. |

No `POST` — relay group is created automatically when needed.

### User data deletion

The existing `DELETE /api/user/data` route must also call `session_manager.delete_relay_group()` during teardown, before logging out the accounts. This ensures no stale relay groups persist in Telegram.

## Pydantic Model Changes

### TransferProgress

Add optional `mode` field to `TransferProgress` in `app/models.py`:

```python
mode: str | None = None  # "forward", "relay_forward", or "copy"
```

### TransferMode enum

`TransferMode` enum keeps only `forward` and `copy` (user-facing choices). `relay_forward` is an internal effective mode, not user-selectable. The `transfers` DB table stores the user's chosen mode (`forward` or `copy`); the effective mode is determined at runtime.

## Frontend UI

### Settings area

```
┌─ Relay Group ──────────────────────────────┐
│  Status: ● Active (created 2026-03-15)     │
│  Group ID: -100123456789                   │
│                                            │
│  [Clear Messages]  [Delete Group]          │
└────────────────────────────────────────────┘
```

- When no relay group exists: "Not created. Will be created automatically when needed."
- Destructive actions require confirmation dialog.

### Transfer progress

SSE progress events include `mode` field:

```json
{"type": "progress", "mode": "relay_forward", "transferred": 42, "total": 100}
```

Frontend can display contextual hint like "Forwarding via relay group".

## Error Handling

### Relay group creation failures

| Scenario | Action |
|----------|--------|
| Account A restricted from creating groups | Fall back to copy mode, log warning |
| Invite link creation fails | Fall back to copy mode |
| Account B join fails | Retry with new invite link once, then fall back |
| DB has stale group ID (group deleted externally) | Clear DB record, recreate |

### Relay forward runtime failures

| Scenario | Action |
|----------|--------|
| A→relay fails with `ChatForwardsRestrictedError` | **Entire job downgrades** to copy mode. Intercepted in `_transfer_message()` before `classify()` — current message retried in copy mode. |
| A→relay fails with `FloodWaitError` | Existing FloodWait strategy (wait + slow down) |
| B→destination fails with `FloodWaitError` | Same |
| B→destination fails with `ChatWriteForbiddenError` | Skip message (existing skip strategy) |
| Relay cleanup fails | Best-effort, log only, no impact on transfer |

### Principles

- **Downgrade is irreversible** (within a session): Once relay_forward → copy, never retry relay in the same job run.
- **Cleanup failure is not an error**: Does not affect transfer success/failure.
- **Error strategy framework unchanged**: `error_strategies.py` Fail/Skip/Pause/Retry classifications apply as-is. `ChatForwardsRestrictedError` interception for mode downgrade is handled in `_transfer_message()` before reaching `classify()`.

## Configuration

New settings in `app/config.py`:

```python
relay_forward_base_delay: float = 4.0       # 4s + 40% jitter (used by RateLimiter)
live_relay_cleanup_threshold: int = 10       # For LiveForwarder
relay_group_title: str = "TMM Relay"         # Supergroup name
```

Note: TransferEngine relay cleanup piggybacks on the existing `batch_size` setting — no separate config needed.

## Out of Scope

- Source-side forward (Account A forward directly to destination) — excluded by design decision (YAGNI).
- Auto-joining Account A to destination groups — too invasive, leaves traces.
- Relay group for copy mode — copy mode doesn't use forwarding, relay adds no value.
- Multiple relay groups — one per user is sufficient.
