import asyncio
import logging
from pathlib import Path
from typing import Literal

from telethon import TelegramClient
from telethon.sessions import SQLiteSession

_CONNECT_TIMEOUT = 10.0  # seconds
_log = logging.getLogger(__name__)

AccountKey = Literal["account_a", "account_b"]


def opposite_account(account: AccountKey) -> AccountKey:
    """Return the other account key."""
    return "account_b" if account == "account_a" else "account_a"


class SessionManager:
    """Manages two independent Telethon client sessions."""

    def __init__(self, api_id: int, api_hash: str, session_dir: Path | None = None) -> None:
        self._clients: dict[AccountKey, TelegramClient] = {}
        self._api_id = api_id
        self._api_hash = api_hash
        self._session_dir = session_dir  # None = use StringSession (multi-user)
        self._relay_group_id: int | None = None
        self._relay_entity_a = None
        self._relay_entity_b = None
        self._relay_lock = asyncio.Lock()

    def _create_client(self, account: AccountKey, session_string: str | None = None) -> TelegramClient:
        from .config import get_settings

        s = get_settings()
        if session_string:
            from telethon.sessions import StringSession

            session = StringSession(session_string)
        elif self._session_dir:
            self._session_dir.mkdir(parents=True, exist_ok=True)
            session = SQLiteSession(str(self._session_dir / account))
        else:
            from telethon.sessions import StringSession

            session = StringSession()  # empty new session
        return TelegramClient(
            session,
            self._api_id,
            self._api_hash,
            flood_sleep_threshold=s.flood_sleep_threshold,
            request_retries=s.request_retries,
            connection_retries=s.connection_retries,
            auto_reconnect=True,
        )

    def get_client(self, account: AccountKey, session_string: str | None = None) -> TelegramClient:
        if account not in self._clients:
            self._clients[account] = self._create_client(account, session_string)
        return self._clients[account]

    def set_client(self, account: AccountKey, client: TelegramClient) -> None:
        """Register an authenticated client for the given account."""
        self._clients[account] = client

    @property
    def relay_group_id(self) -> int | None:
        """The Telegram group ID used for relay forwarding, or None."""
        return self._relay_group_id

    @property
    def relay_entity_a(self):
        """The resolved relay group entity for Account A, or None."""
        return self._relay_entity_a

    def get_session_string(self, account: AccountKey) -> str | None:
        """Get the StringSession string for serialization/encryption."""
        client = self._clients.get(account)
        if client and hasattr(client.session, "save"):
            return client.session.save()
        return None

    async def is_authorized(self, account: AccountKey) -> bool:
        client = self.get_client(account)
        if not client.is_connected():
            await asyncio.wait_for(client.connect(), timeout=_CONNECT_TIMEOUT)
        return await client.is_user_authorized()

    async def get_user_info(self, account: AccountKey) -> dict | None:
        if not await self.is_authorized(account):
            return None
        me = await self.get_client(account).get_me()
        return {
            "phone": me.phone or "",
            "name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
            "username": me.username,
        }

    async def connect_all(self) -> None:
        for account in ("account_a", "account_b"):
            client = self.get_client(account)
            if not client.is_connected():
                try:
                    await asyncio.wait_for(client.connect(), timeout=_CONNECT_TIMEOUT)
                except (TimeoutError, OSError) as e:
                    _log.warning("Failed to connect %s on startup: %s", account, e)

    async def disconnect_all(self) -> None:
        for client in self._clients.values():
            if client.is_connected():
                await client.disconnect()
        self._clients.clear()

    async def ensure_relay_group(self, db=None, user_token: str | None = None):
        """Return (relay_entity_a, relay_entity_b), creating the group if needed."""
        async with self._relay_lock:
            if self._relay_entity_a and self._relay_entity_b:
                return self._relay_entity_a, self._relay_entity_b

            source = self._clients.get("account_a")
            dest = self._clients.get("account_b")
            if not source or not dest:
                raise RuntimeError("Both accounts must be connected")

            # Try loading from DB
            if db and user_token and self._relay_group_id is None:
                from .database import get_relay_group

                record = await get_relay_group(db, user_token)
                if record:
                    self._relay_group_id = record["group_id"]

            # Verify existing group is accessible
            if self._relay_group_id:
                try:
                    self._relay_entity_a = await source.get_entity(self._relay_group_id)
                    self._relay_entity_b = await dest.get_entity(self._relay_group_id)
                    return self._relay_entity_a, self._relay_entity_b
                except Exception:
                    self._relay_group_id = None
                    self._relay_entity_a = None
                    self._relay_entity_b = None
                    if db and user_token:
                        from .database import delete_relay_group_record

                        await delete_relay_group_record(db, user_token)

            # Create new supergroup
            from telethon.tl.functions.channels import CreateChannelRequest
            from telethon.tl.functions.messages import (
                ExportChatInviteRequest,
                ImportChatInviteRequest,
            )

            from .config import get_settings

            s = get_settings()
            result = await source.__call__(CreateChannelRequest(title=s.relay_group_title, about="", megagroup=True))
            group_id = result.chats[0].id
            self._relay_group_id = group_id

            entity_a = await source.get_entity(group_id)
            invite = await source.__call__(ExportChatInviteRequest(entity_a))

            invite_hash = invite.link.split("/")[-1]
            if invite_hash.startswith("+"):
                invite_hash = invite_hash[1:]
            try:
                await dest.__call__(ImportChatInviteRequest(invite_hash))
            except Exception:
                invite = await source.__call__(ExportChatInviteRequest(entity_a))
                invite_hash = invite.link.split("/")[-1]
                if invite_hash.startswith("+"):
                    invite_hash = invite_hash[1:]
                await dest.__call__(ImportChatInviteRequest(invite_hash))

            self._relay_entity_a = entity_a
            self._relay_entity_b = await dest.get_entity(group_id)

            if db and user_token:
                from .database import save_relay_group

                await save_relay_group(db, user_token, group_id)

            return self._relay_entity_a, self._relay_entity_b

    async def delete_relay_group(self, db=None, user_token: str | None = None) -> None:
        """Delete the relay group from Telegram and clear all state."""
        telegram_deleted = True
        if self._relay_group_id and self._relay_entity_a:
            try:
                from telethon.tl.functions.channels import DeleteChannelRequest

                source = self._clients.get("account_a")
                if source:
                    await source.__call__(DeleteChannelRequest(self._relay_entity_a))
            except Exception:
                _log.warning(
                    "Failed to delete relay group %s from Telegram — group may be orphaned",
                    self._relay_group_id,
                    exc_info=True,
                )
                telegram_deleted = False

        if not telegram_deleted:
            _log.error(
                "Relay group %s still exists on Telegram but local references will be cleared",
                self._relay_group_id,
            )

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
                await source.__call__(DeleteMessagesRequest(self._relay_entity_a, message_ids))
        except Exception as e:
            _log.debug("Relay cleanup failed: %s", e)
