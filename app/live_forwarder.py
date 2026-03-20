"""Live forwarding: monitor a source chat and forward/copy new messages in real-time."""

import asyncio
import logging

from telethon import errors as tg_errors
from telethon import events

from .config import get_settings
from .error_strategies import Strategy, classify
from .event_broadcaster import EventBroadcaster
from .message_copy import copy_message
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class LiveForwarder(EventBroadcaster):
    """Monitors a source chat and forwards/copies incoming messages to a destination."""

    def __init__(self, session_manager=None) -> None:
        super().__init__()
        self._session_manager = session_manager
        self.active: bool = False
        self.source_chat_id: int = 0
        self.dest_entity = None
        self.source_entity_b = None
        self.mode: str = "forward"
        self.keyword_whitelist: list[str] = []
        self.keyword_blacklist: list[str] = []
        self.include_text: bool = True
        self.include_media: bool = True

        self.stats = {"forwarded": 0, "failed": 0, "skipped": 0}
        self.rate_limiter = RateLimiter()
        self._handler = None
        self._relay_a = None
        self._relay_b = None
        self._pending_relay_ids: list[int] = []

    async def start(
        self,
        source_chat_id: int,
        mode: str = "forward",
        target_type: str = "saved_messages",
        target_chat_id: int | None = None,
        include_text: bool = True,
        include_media: bool = True,
        keyword_whitelist: str = "",
        keyword_blacklist: str = "",
    ) -> None:
        if self.active:
            raise RuntimeError("Live forwarder already running")

        self.source_chat_id = source_chat_id
        self.mode = mode
        self.include_text = include_text
        self.include_media = include_media
        self.keyword_whitelist = [k.strip().lower() for k in keyword_whitelist.split(",") if k.strip()]
        self.keyword_blacklist = [k.strip().lower() for k in keyword_blacklist.split(",") if k.strip()]
        self.stats = {"forwarded": 0, "failed": 0, "skipped": 0}
        self.rate_limiter.reset()

        source_client = self._session_manager.get_client("account_a")
        dest_client = self._session_manager.get_client("account_b")

        # Resolve destination
        if target_type == "saved_messages":
            self.dest_entity = await dest_client.get_me()
        else:
            self.dest_entity = await dest_client.get_entity(target_chat_id)

        # Resolve source for Account B (forward mode needs it)
        self.source_entity_b = None
        effective_mode = mode

        # Check if source is a private chat (Account A's perspective)
        # Cache the entity for reuse in _handle_message relay_forward branch
        try:
            source_entity = await source_client.get_entity(source_chat_id)
            from telethon.tl.types import User

            is_private = isinstance(source_entity, User)
        except Exception:
            is_private = True
            source_entity = None
        self._source_entity_a = source_entity

        if is_private and mode == "forward":
            # Private chat: Account B can't forward directly, but Account A
            # can forward via relay group (A has access to its own private chats)
            try:
                self._relay_a, self._relay_b = await self._session_manager.ensure_relay_group()
                effective_mode = "relay_forward"
                logger.info("Private chat: live forwarder using relay group")
            except Exception:
                logger.warning("Relay unavailable for private chat, falling back to copy")
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

        # Register Telethon event handler
        @source_client.on(events.NewMessage(chats=source_chat_id))
        async def on_new_message(event):
            await self._handle_message(event, dest_client)

        self._handler = on_new_message
        self.active = True
        logger.info("Live forwarder started: chat %d → %s mode", source_chat_id, self.mode)
        self._broadcast_sync("live_started", {"source_chat_id": source_chat_id, "mode": self.mode})

    async def stop(self) -> None:
        if not self.active:
            return
        source_client = self._session_manager.get_client("account_a")
        if self._handler:
            source_client.remove_event_handler(self._handler)
            self._handler = None
        # Final relay cleanup
        if self._pending_relay_ids and self._session_manager:
            try:
                await self._session_manager.cleanup_relay_messages(self._pending_relay_ids)
            except Exception:
                logger.warning("Relay cleanup failed on stop", exc_info=True)
            finally:
                self._pending_relay_ids.clear()
        self.active = False
        logger.info("Live forwarder stopped. Stats: %s", self.stats)
        self._broadcast_sync("live_stopped", self.stats.copy())

    async def _handle_message(self, event, dest_client) -> None:
        msg = event.message

        # Skip service messages
        if msg.action:
            return

        # Type filters
        has_media = msg.media is not None
        has_text = bool(msg.text)
        if has_media and not has_text and not self.include_media:
            self.stats["skipped"] += 1
            return
        if has_text and not has_media and not self.include_text:
            self.stats["skipped"] += 1
            return

        # Keyword filters
        text_lower = (msg.text or "").lower()
        if self.keyword_whitelist and text_lower:
            if not any(k in text_lower for k in self.keyword_whitelist):
                self.stats["skipped"] += 1
                return
        if self.keyword_blacklist and text_lower:
            if any(k in text_lower for k in self.keyword_blacklist):
                self.stats["skipped"] += 1
                return

        # Rate limit
        op = (
            "relay_forward"
            if self.mode == "relay_forward"
            else ("forward" if self.mode == "forward" else ("copy_file" if has_media else "copy_text"))
        )
        await self.rate_limiter.acquire(op)

        # Transfer
        try:
            if self.mode == "forward":
                await dest_client.forward_messages(self.dest_entity, msg.id, self.source_entity_b)
            elif self.mode == "relay_forward":
                source_client = self._session_manager.get_client("account_a")
                relay_result = await source_client.forward_messages(self._relay_a, msg.id, self._source_entity_a)
                # forward_messages returns a single Message for a single ID, not a list
                relay_msg_id = relay_result.id if not isinstance(relay_result, list) else relay_result[0].id
                self._pending_relay_ids.append(relay_msg_id)
                await dest_client.forward_messages(self.dest_entity, relay_msg_id, self._relay_b)
                # Threshold cleanup
                if len(self._pending_relay_ids) >= get_settings().live_relay_cleanup_threshold:
                    await self._session_manager.cleanup_relay_messages(self._pending_relay_ids)
                    self._pending_relay_ids.clear()
            else:
                await self._copy_message(dest_client, msg)
            self.stats["forwarded"] += 1
            self._broadcast_sync("live_message", {"message_id": msg.id, "status": "done"})
        except Exception as exc:
            # Intercept forwards-restricted in relay mode — downgrade to copy
            if self.mode == "relay_forward" and isinstance(exc, tg_errors.ChatForwardsRestrictedError):
                logger.warning("Source forbids forwarding, downgrading live forwarder to copy")
                self.mode = "copy"
                try:
                    await self._copy_message(dest_client, msg)
                    self.stats["forwarded"] += 1
                    self._broadcast_sync("live_message", {"message_id": msg.id, "status": "done"})
                    return
                except Exception as copy_exc:
                    exc = copy_exc  # fall through to normal error handling

            strategy, reason = classify(exc)
            logger.warning("Live forward msg %d: %s → %s", msg.id, reason, strategy)

            if strategy == Strategy.pause and isinstance(exc, tg_errors.FloodWaitError):
                self._broadcast_sync("live_rate_limited", {"wait_seconds": exc.seconds})
                await asyncio.sleep(exc.seconds * get_settings().flood_extra_buffer)
                self.rate_limiter.record_flood_wait()
            elif strategy == Strategy.fail:
                self.stats["failed"] += 1
                self._broadcast_sync("live_error", {"message_id": msg.id, "error": reason, "fatal": True})
                await self.stop()
                return
            else:
                self.stats["failed"] += 1
                self._broadcast_sync("live_error", {"message_id": msg.id, "error": reason, "fatal": False})

    async def _copy_message(self, dest_client, msg) -> None:
        await copy_message(dest_client, self.dest_entity, msg)
