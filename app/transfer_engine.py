import asyncio
import logging
import time
import uuid
from datetime import UTC, timedelta

from telethon import errors as tg_errors

from .config import get_settings
from .database import (
    create_transfer,
    get_all_done_msg_ids_for_chat,
    get_db,
    get_processed_msg_ids,
    record_message,
    update_transfer_status,
)
from .error_strategies import Strategy, classify
from .event_broadcaster import EventBroadcaster
from .message_copy import copy_message
from .models import TransferJobCreate, TransferProgress, TransferStatus
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


# Return values for _transfer_message
_DONE = "done"
_SKIPPED = "skipped"
_FAILED = "failed"


class TransferEngine(EventBroadcaster):
    """Executes a message transfer job with pause/cancel support."""

    def __init__(
        self,
        session_manager=None,
        semaphore=None,
        max_messages: int = 50000,
        persist_checkpoints: bool = True,
    ) -> None:
        super().__init__()
        self._session_manager = session_manager
        self._semaphore = semaphore
        self._max_messages = max_messages
        self._persist_checkpoints = persist_checkpoints

        self.job_id: str = ""
        self.config: TransferJobCreate | None = None
        self.status: TransferStatus = TransferStatus.pending
        self.progress = TransferProgress()
        self.rate_limiter = RateLimiter()

        self._task: asyncio.Task | None = None
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # not paused initially
        self._cancelled = False
        self._effective_mode: str = "forward"
        self._relay_a = None
        self._relay_b = None
        self._pending_relay_ids: list[int] = []
        self._source_entity_a = None

    # ── SSE broadcasting ──────────────────────────────

    def subscribe(self) -> asyncio.Queue:
        q = super().subscribe()
        # Replay current state for late-joining subscribers (fixes race condition
        # where the task sends events before the SSE connection is established)
        if self.status != TransferStatus.pending:
            q.put_nowait({"type": "progress", "data": self.progress.model_dump()})
        if self.status in (TransferStatus.completed, TransferStatus.failed, TransferStatus.cancelled):
            terminal = {
                "total": self.progress.total_messages,
                "transferred": self.progress.transferred_count,
                "failed": self.progress.failed_count,
                "skipped": self.progress.skipped_count,
                "elapsed": round(self.progress.elapsed_seconds, 1),
            }
            if self.status == TransferStatus.failed:
                terminal["error"] = self.progress.last_error or "Unknown error"
            q.put_nowait({"type": f"job_{self.status.value}", "data": terminal})
        return q

    # ── Job lifecycle ─────────────────────────────────

    async def start(self, config: TransferJobCreate) -> str:
        # Guard against concurrent jobs
        if self._task and not self._task.done():
            raise RuntimeError("A transfer is already in progress")

        self.job_id = str(uuid.uuid4())[:8]
        self.config = config
        self.status = TransferStatus.pending
        self.progress = TransferProgress()
        self.rate_limiter.reset()
        self._cancelled = False
        self._pause_event.set()
        self._effective_mode = config.mode.value

        if self._persist_checkpoints:
            db = await get_db()
            try:
                await create_transfer(
                    db,
                    self.job_id,
                    config.source_chat_id,
                    config.target_chat_id,
                    config.mode.value,
                    config.target_type.value,
                    config.model_dump(mode="json"),
                )
            finally:
                await db.close()

        self._task = asyncio.create_task(self._run())
        return self.job_id

    def pause(self) -> None:
        if self.status == TransferStatus.running:
            self._pause_event.clear()
            self.status = TransferStatus.paused

    def resume(self) -> None:
        if self.status == TransferStatus.paused:
            self._pause_event.set()
            self.status = TransferStatus.running

    def cancel(self) -> None:
        self._cancelled = True
        self._pause_event.set()  # unblock if paused
        self.status = TransferStatus.cancelled

    # ── Core transfer loop ────────────────────────────

    async def _run(self) -> None:
        if self._semaphore:
            async with self._semaphore:
                await self._run_inner()
        else:
            await self._run_inner()

    async def _run_inner(self) -> None:
        self.status = TransferStatus.running
        start_time = time.time()

        db = None
        if self._persist_checkpoints:
            db = await get_db()

        try:
            cfg = self.config
            from .telegram_client import opposite_account

            source_account = cfg.source_account
            target_account = opposite_account(source_account)
            source_client = self._session_manager.get_client(source_account)
            dest_client = self._session_manager.get_client(target_account)

            # Resolve target entity (must be resolved by dest_client)
            if cfg.target_type.value == "saved_messages":
                dest_entity = await dest_client.get_me()
            else:
                dest_entity = await dest_client.get_entity(cfg.target_chat_id)

            # Resolve source entity for Account B (needed for forward mode)
            # Account B must also be able to see the source chat
            source_entity_b = None

            # If source is a private/user chat, forward mode won't work —
            # Account B can't see Account A's private messages.
            try:
                source_entity_a = await source_client.get_entity(cfg.source_chat_id)
                from telethon.tl.types import User

                is_private = isinstance(source_entity_a, User)
            except Exception:
                is_private = True
                source_entity_a = None

            if is_private and self._effective_mode == "forward":
                # Private chat: Account B can't forward directly, but Account A
                # can forward via relay group (A has access to its own private chats)
                try:
                    self._relay_a, self._relay_b = await self._session_manager.ensure_relay_group()
                    self._effective_mode = "relay_forward"
                    logger.info("Private chat: using relay group for forwarding")
                except Exception:
                    logger.warning("Relay group unavailable for private chat, falling back to copy mode")
                    self._effective_mode = "copy"
            elif self._effective_mode == "forward":
                try:
                    source_entity_b = await dest_client.get_entity(cfg.source_chat_id)
                except Exception:
                    try:
                        self._relay_a, self._relay_b = await self._session_manager.ensure_relay_group()
                        self._effective_mode = "relay_forward"
                        logger.info("Using relay group for forwarding")
                    except Exception:
                        logger.warning("Relay group unavailable, falling back to copy mode")
                        self._effective_mode = "copy"

            # Store source_entity_a for reuse in _transfer_message relay_forward branch
            self._source_entity_a = source_entity_a

            self.progress.mode = self._effective_mode

            # Apply account age multiplier for newer accounts
            await self._apply_account_age_multiplier(dest_client)

            # Get already-processed IDs for resume — check BOTH this job
            # AND all previous jobs for the same source→dest pair (prevents duplicates
            # when resuming after server restart creates a new job_id).
            if self._persist_checkpoints:
                processed = await get_processed_msg_ids(db, self.job_id)
                previously_done = await get_all_done_msg_ids_for_chat(
                    db,
                    cfg.source_chat_id,
                    cfg.target_chat_id,
                )
                processed |= previously_done
            else:
                processed = set()  # no persistent dedup in multi-user mode

            # Collect message objects in one pass (newest→oldest, Telegram default).
            # We avoid reverse=True (hangs on some chat types) and avoid
            # re-fetching by ID (triggers throttling after fast collection).
            # Date range is applied here so total_messages reflects actual work.
            logger.info("Collecting messages from source chat...")
            all_messages = []

            # Use offset_date to skip messages newer than date_to
            iter_kwargs: dict = {}
            date_to = None
            if cfg.date_to:
                date_to = cfg.date_to if cfg.date_to.tzinfo else cfg.date_to.replace(tzinfo=UTC)
                # offset_date is exclusive upper bound; add 1 day to include date_to
                iter_kwargs["offset_date"] = date_to + timedelta(days=1)

            date_from = None
            if cfg.date_from:
                date_from = cfg.date_from if cfg.date_from.tzinfo else cfg.date_from.replace(tzinfo=UTC)

            # Pre-parse keyword filters (once, not per-message)
            whitelist_kws = (
                [k.strip().lower() for k in cfg.keyword_whitelist.split(",") if k.strip()]
                if cfg.keyword_whitelist else []
            )
            blacklist_kws = (
                [k.strip().lower() for k in cfg.keyword_blacklist.split(",") if k.strip()]
                if cfg.keyword_blacklist else []
            )

            async for msg in source_client.iter_messages(cfg.source_chat_id, **iter_kwargs):
                if msg.action:
                    continue
                # Stop collecting once we pass date_from (messages are newest→oldest)
                if date_from and msg.date and msg.date < date_from:
                    break
                all_messages.append(msg)
                if len(all_messages) >= self._max_messages:
                    logger.warning("Message collection capped at %d", self._max_messages)
                    break
            all_messages.reverse()  # oldest→newest for chronological order in dest

            total = len(all_messages)
            self.progress.total_messages = total
            if self._persist_checkpoints:
                await update_transfer_status(db, self.job_id, "running", total_messages=total)
            await self._broadcast("progress", self.progress.model_dump())
            logger.info("Collected %d messages, starting transfer", total)

            for msg in all_messages:
                # Check cancellation
                if self._cancelled:
                    break

                # Check pause
                if not self._pause_event.is_set():
                    await self._broadcast("job_paused", {})
                    if self._persist_checkpoints:
                        await update_transfer_status(
                            db,
                            self.job_id,
                            "paused",
                            transferred_count=self.progress.transferred_count,
                            failed_count=self.progress.failed_count,
                        )
                    await self._pause_event.wait()
                    if self._cancelled:
                        break
                    self.status = TransferStatus.running
                    await self._broadcast("job_resumed", {})

                # Helper: skip a message and periodically broadcast progress
                def _skip():
                    self.progress.skipped_count += 1

                async def _maybe_broadcast_skip():
                    """Broadcast progress every 20 skips so the UI stays responsive."""
                    if self.progress.skipped_count % 20 == 0:
                        self.progress.elapsed_seconds = time.time() - start_time
                        await self._broadcast("progress", self.progress.model_dump())

                # Date range filter (messages are oldest→newest)
                if date_from and msg.date and msg.date < date_from:
                    _skip()
                    await _maybe_broadcast_skip()
                    continue
                if date_to and msg.date and msg.date > date_to:
                    break  # past the end

                # Skip already processed (resume)
                if msg.id in processed:
                    _skip()
                    await _maybe_broadcast_skip()
                    continue

                # Message type filters
                has_media = msg.media is not None
                has_text = bool(msg.text)
                if has_media and not has_text and not cfg.include_media:
                    _skip()
                    continue
                if has_text and not has_media and not cfg.include_text:
                    _skip()
                    continue
                # File size filter (copy mode only — forward doesn't re-upload)
                if self._effective_mode == "copy" and cfg.max_file_size_mb and has_media and msg.file:
                    size_mb = (msg.file.size or 0) / (1024 * 1024)
                    if size_mb > cfg.max_file_size_mb:
                        _skip()
                        continue

                # Keyword filters (case-insensitive, pre-parsed before loop)
                text_lower = (msg.text or "").lower()
                if whitelist_kws:
                    if text_lower and not any(k in text_lower for k in whitelist_kws):
                        _skip()
                        continue
                if blacklist_kws:
                    if text_lower and any(k in text_lower for k in blacklist_kws):
                        _skip()
                        continue

                # Daily cap check
                if self.rate_limiter.check_daily_cap():
                    self.progress.last_error = "Daily message cap reached"
                    await self._broadcast("daily_cap", {"remaining": 0})
                    self.pause()
                    await self._pause_event.wait()
                    if self._cancelled:
                        break

                # Rate limit (use effective mode, not config mode)
                op = self._get_op_type(msg)
                logger.debug("Acquiring rate limit for msg #%d (op=%s)", msg.id, op)
                await asyncio.wait_for(self.rate_limiter.acquire(op), timeout=30.0)

                # Transfer the message
                logger.debug("Transferring msg #%d (mode=%s)", msg.id, self._effective_mode)
                result = await self._transfer_message(
                    db, source_client, dest_client, dest_entity, source_entity_b, msg, self._effective_mode
                )

                if result == _DONE:
                    self.progress.transferred_count += 1
                    self.rate_limiter.increment_daily()
                elif result == _SKIPPED:
                    self.progress.skipped_count += 1
                else:
                    self.progress.failed_count += 1

                # Update progress
                self.progress.current_message_id = msg.id
                self.progress.elapsed_seconds = time.time() - start_time
                done = self.progress.transferred_count + self.progress.failed_count + self.progress.skipped_count
                total = self.progress.total_messages
                if total > 0 and done <= total:
                    self.progress.percent = done / total * 100
                elif total > 0:
                    # done exceeded total (filtered messages counted differently)
                    self.progress.percent = 99.0
                # else: total is 0 (unreliable for some chats), leave percent at 0

                if self.progress.transferred_count > 0 and self.progress.elapsed_seconds > 0 and total > done:
                    rate = self.progress.transferred_count / self.progress.elapsed_seconds
                    remaining = total - done
                    self.progress.estimated_remaining_seconds = remaining / rate if rate > 0 else None
                else:
                    self.progress.estimated_remaining_seconds = None

                await self._broadcast("progress", self.progress.model_dump())

                # Batch cooldown
                await self.rate_limiter.batch_cooldown()

                # Batch commit + relay cleanup during batch cooldown
                if self.rate_limiter._batch_counter % get_settings().batch_size == 0:
                    if self._persist_checkpoints and db:
                        await db.commit()
                    if self._pending_relay_ids:
                        await self._session_manager.cleanup_relay_messages(self._pending_relay_ids)
                        self._pending_relay_ids.clear()

                # Try to recover rate
                self.rate_limiter.try_recover_rate()

            # Final status
            if self._cancelled:
                self.status = TransferStatus.cancelled
                final = "cancelled"
            else:
                self.status = TransferStatus.completed
                final = "completed"

            if self._persist_checkpoints:
                await update_transfer_status(
                    db,
                    self.job_id,
                    final,
                    transferred_count=self.progress.transferred_count,
                    failed_count=self.progress.failed_count,
                    skipped_count=self.progress.skipped_count,
                )
            await self._broadcast(
                f"job_{final}",
                {
                    "total": self.progress.total_messages,
                    "transferred": self.progress.transferred_count,
                    "failed": self.progress.failed_count,
                    "skipped": self.progress.skipped_count,
                    "elapsed": round(self.progress.elapsed_seconds, 1),
                },
            )

        except Exception as e:
            logger.exception("Transfer failed")
            self.status = TransferStatus.failed
            _strategy, reason = classify(e)
            self.progress.last_error = reason
            if self._persist_checkpoints:
                await update_transfer_status(db, self.job_id, "failed")
            await self._broadcast("job_failed", {"error": reason})
        finally:
            # Final relay cleanup
            if self._pending_relay_ids and self._session_manager:
                try:
                    await self._session_manager.cleanup_relay_messages(self._pending_relay_ids)
                except Exception:
                    logger.warning("Relay cleanup failed during transfer finalization", exc_info=True)
                finally:
                    self._pending_relay_ids.clear()
            if db:
                try:
                    await db.commit()
                except Exception:
                    logger.error("Final db.commit() failed — message records may be lost", exc_info=True)
                await db.close()

    async def _transfer_message(
        self,
        db,
        source_client,
        dest_client,
        dest_entity,
        source_entity_b,
        msg,
        mode: str,
    ) -> str:
        """Transfer a single message using strategy-based error recovery."""
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                if mode == "forward":
                    await dest_client.forward_messages(dest_entity, msg.id, source_entity_b)
                elif mode == "relay_forward":
                    relay_result = await source_client.forward_messages(self._relay_a, msg.id, self._source_entity_a)
                    # forward_messages returns a single Message for a single ID, not a list
                    relay_msg_id = relay_result.id if not isinstance(relay_result, list) else relay_result[0].id
                    self._pending_relay_ids.append(relay_msg_id)
                    await dest_client.forward_messages(dest_entity, relay_msg_id, self._relay_b)
                else:
                    await self._copy_message(dest_client, dest_entity, msg)

                if self._persist_checkpoints:
                    await record_message(db, self.job_id, msg.id, "done")
                await self._broadcast("message_transferred", {"message_id": msg.id})
                return _DONE

            except Exception as exc:
                # Intercept ChatForwardsRestrictedError in relay_forward mode
                if mode == "relay_forward" and isinstance(exc, tg_errors.ChatForwardsRestrictedError):
                    logger.warning("Source chat forbids forwarding, downgrading to copy mode")
                    self._effective_mode = "copy"
                    self.progress.mode = "copy"
                    return await self._transfer_message(
                        db, source_client, dest_client, dest_entity, source_entity_b, msg, "copy"
                    )

                strategy, reason = classify(exc)
                logger.warning("msg %d attempt %d: %s → %s", msg.id, attempt + 1, reason, strategy)

                if strategy == Strategy.fail:
                    auth_errors = (
                        tg_errors.AuthKeyUnregisteredError,
                        tg_errors.UserDeactivatedBanError,
                        tg_errors.UserDeactivatedError,
                    )
                    if isinstance(exc, auth_errors):
                        await self._broadcast("auth_expired", {"reason": reason})
                    raise  # propagate to _run_inner()

                if strategy == Strategy.skip:
                    if self._persist_checkpoints:
                        await record_message(db, self.job_id, msg.id, "skipped", error=reason)
                    await self._broadcast("message_skipped", {"message_id": msg.id, "reason": reason})
                    return _SKIPPED

                if strategy == Strategy.pause:
                    # FloodWait-specific handling
                    if isinstance(exc, tg_errors.FloodWaitError):
                        self.progress.is_rate_limited = True
                        self.progress.rate_limit_wait_seconds = exc.seconds
                        await self._broadcast("rate_limited", {"wait_seconds": exc.seconds})
                        await asyncio.sleep(exc.seconds * get_settings().flood_extra_buffer)
                        self.progress.is_rate_limited = False
                        self.progress.rate_limit_wait_seconds = None
                        self.rate_limiter.record_flood_wait()

                        if self.rate_limiter.should_auto_pause():
                            self.progress.last_error = "Auto-paused: too many FloodWaits"
                            await self._broadcast("auto_paused", {"reason": "flood_limit"})
                            self.pause()
                            await self._pause_event.wait()
                            if self._cancelled:
                                return _FAILED
                    continue  # retry after pause

                # Strategy.retry — exponential backoff
                if attempt == max_attempts - 1:
                    if self._persist_checkpoints:
                        await record_message(db, self.job_id, msg.id, "failed", error=reason)
                    await self._broadcast("message_failed", {"message_id": msg.id, "error": reason})
                    return _FAILED
                await asyncio.sleep(2**attempt)

        return _FAILED

    def _make_progress_cb(self, msg_id: int, phase: str, total_bytes: int):
        """Create a Telethon progress_callback that broadcasts download/upload %."""
        last_pct = [-1]  # mutable for closure

        def callback(current, total):
            t = total or total_bytes
            pct = int(current / t * 100) if t else 0
            # Only broadcast every 10% to avoid flooding SSE
            bucket = pct // 10 * 10
            if bucket != last_pct[0]:
                last_pct[0] = bucket
                size_mb = round(t / (1024 * 1024), 1)
                self._broadcast_sync(
                    "file_progress",
                    {
                        "message_id": msg_id,
                        "phase": phase,
                        "percent": pct,
                        "size_mb": size_mb,
                    },
                )

        return callback

    _UPLOAD_LIMIT = 2 * 1024 * 1024 * 1024  # 2GB — Telegram non-Premium upload limit

    async def _copy_message(self, dest_client, dest_entity, msg) -> None:
        """Download media from source, re-send via dest account."""
        await copy_message(
            dest_client, dest_entity, msg,
            progress_cb=self._make_progress_cb,
            upload_limit=self._UPLOAD_LIMIT,
        )

    async def _apply_account_age_multiplier(self, dest_client) -> None:
        """Check destination account age and slow down rate for newer accounts."""
        try:
            me = await dest_client.get_me()
            # Telethon User objects don't expose creation date directly,
            # but we can check if the user has a premium flag or use the
            # account's oldest known activity. As a practical proxy, we use
            # the "date" field from the full user object if available.
            # If unavailable, assume a mature account (no multiplier).
            from telethon.tl.functions.users import GetFullUserRequest

            full = await dest_client(GetFullUserRequest(me))
            # full.users[0] may have a "date" field in some API layers
            user_date = getattr(full.users[0] if full.users else me, "date", None)
            if user_date:
                from datetime import datetime

                age_days = (datetime.now(UTC) - user_date).days
                settings = get_settings()
                if age_days < settings.new_account_days:
                    self.rate_limiter.set_account_age_multiplier(settings.new_account_multiplier)
                    logger.info(
                        "New account detected (%d days), applying %.1fx delay multiplier",
                        age_days,
                        settings.new_account_multiplier,
                    )
                elif age_days < settings.medium_account_days:
                    self.rate_limiter.set_account_age_multiplier(settings.medium_account_multiplier)
                    logger.info(
                        "Medium-age account (%d days), applying %.1fx delay multiplier",
                        age_days,
                        settings.medium_account_multiplier,
                    )
        except Exception:
            logger.debug("Could not determine account age, using default rates")

    def _get_op_type(self, msg) -> str:
        if self._effective_mode == "forward":
            return "forward"
        if self._effective_mode == "relay_forward":
            return "relay_forward"
        if msg.media:
            return "copy_file"
        return "copy_text"
