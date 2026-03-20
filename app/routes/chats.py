"""Chat routes — JSON API for listing dialogs and messages.

Supports both SINGLE_USER_MODE (global SessionManager on app.state) and
multi-user mode (per-user contexts via session_id cookie).
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from telethon.tl import types

from ..middleware import resolve_session_manager
from ..models import ChatInfo, ChatListResponse, MessageInfo, MessageListResponse
from ..telegram_client import AccountKey

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chats", tags=["chats"])


# ── Pure helper functions ─────────────────────────────────────────────


def _classify_entity(entity) -> str:
    if isinstance(entity, types.User):
        return "user"
    if isinstance(entity, types.Channel):
        return "supergroup" if entity.megagroup else "channel"
    if isinstance(entity, types.Chat):
        return "group"
    return "user"


def _dialog_to_chat(dialog) -> ChatInfo:
    entity = dialog.entity
    title = dialog.title or ""
    if isinstance(entity, types.User):
        title = f"{entity.first_name or ''} {entity.last_name or ''}".strip() or title
    return ChatInfo(
        id=dialog.id,
        title=title,
        type=_classify_entity(entity),
        unread_count=dialog.unread_count or 0,
        last_message_date=dialog.date,
    )


def _msg_to_info(msg) -> MessageInfo:
    sender_name = ""
    if msg.sender:
        if isinstance(msg.sender, types.User):
            sender_name = f"{msg.sender.first_name or ''} {msg.sender.last_name or ''}".strip()
        else:
            sender_name = getattr(msg.sender, "title", "")

    media_type = None
    media_filename = None
    media_size = None
    has_media = msg.media is not None

    if has_media:
        if msg.photo:
            media_type = "photo"
        elif msg.video:
            media_type = "video"
        elif msg.voice:
            media_type = "voice"
        elif msg.audio:
            media_type = "audio"
        elif msg.sticker:
            media_type = "sticker"
        elif msg.gif:
            media_type = "animation"
        elif msg.video_note:
            media_type = "video_note"
        elif msg.document:
            media_type = "document"

        if msg.file:
            media_filename = msg.file.name
            media_size = msg.file.size

    return MessageInfo(
        id=msg.id,
        date=msg.date,
        sender_name=sender_name,
        text=msg.text,
        media_type=media_type,
        media_filename=media_filename,
        media_size=media_size,
        has_media=has_media,
        reply_to_msg_id=msg.reply_to.reply_to_msg_id if msg.reply_to else None,
    )


# ── Endpoints ─────────────────────────────────────────


@router.get("/{account}", response_model=ChatListResponse)
async def list_chats(
    request: Request,
    account: AccountKey,
    limit: int = 50,
    offset: int = 0,
    search: str = "",
    sort: str = "recent",
):
    """List dialogs for the given account, returns JSON."""
    sm = resolve_session_manager(request)
    client = sm.get_client(account)
    if not await sm.is_authorized(account):
        raise HTTPException(status_code=401, detail="Not logged in.")

    # Fetch more than needed when searching (search is client-side filter)
    fetch_limit = limit + offset + (200 if search else 0)
    all_chats: list[ChatInfo] = []
    async for dialog in client.iter_dialogs(limit=fetch_limit):
        info = _dialog_to_chat(dialog)
        if search and search.lower() not in info.title.lower():
            continue
        all_chats.append(info)

    # Sort
    if sort == "name":
        all_chats.sort(key=lambda c: c.title.lower())
    elif sort == "unread":
        all_chats.sort(key=lambda c: c.unread_count, reverse=True)
    # "recent" is default order from Telegram

    total = len(all_chats)
    chats = all_chats[offset : offset + limit]
    has_more = offset + limit < total

    return ChatListResponse(chats=chats, has_more=has_more)


@router.get("/{account}/{chat_id}/messages", response_model=MessageListResponse)
async def list_messages(
    request: Request,
    account: AccountKey,
    chat_id: int,
    limit: int = 50,
    offset_id: int = 0,
    date_from: str | None = None,
    date_to: str | None = None,
):
    """Get messages from a chat, returns JSON."""
    sm = resolve_session_manager(request)
    client = sm.get_client(account)
    if not await sm.is_authorized(account):
        raise HTTPException(status_code=401, detail="Not logged in.")

    kwargs: dict = {"limit": limit}
    if offset_id:
        kwargs["offset_id"] = offset_id
    if date_from:
        kwargs["offset_date"] = datetime.fromisoformat(date_from).replace(tzinfo=UTC)
    if date_to:
        kwargs["min_id"] = 0  # combined with offset_date for range

    messages: list[MessageInfo] = []
    dt_from = datetime.fromisoformat(date_from).replace(tzinfo=UTC) if date_from else None
    dt_to = datetime.fromisoformat(date_to).replace(tzinfo=UTC) if date_to else None

    async for msg in client.iter_messages(chat_id, **kwargs):
        if msg.action:
            continue  # skip service messages
        if dt_to and msg.date and msg.date > dt_to:
            continue
        if dt_from and msg.date and msg.date < dt_from:
            break  # messages are ordered newest→oldest, so stop here
        messages.append(_msg_to_info(msg))

    has_more = len(messages) == limit

    return MessageListResponse(messages=messages, has_more=has_more)


@router.get("/{account}/{chat_id}/date-range")
async def chat_date_range(request: Request, account: AccountKey, chat_id: int):
    """Get date boundaries and total message count for a chat."""
    import asyncio

    sm = resolve_session_manager(request)
    client = sm.get_client(account)
    if not await sm.is_authorized(account):
        raise HTTPException(status_code=401, detail="Not logged in.")

    # Total count (1 RPC, returns .total without fetching messages)
    total_obj = await client.get_messages(chat_id, limit=0)
    total = total_obj.total if total_obj else 0

    # Latest message (1 RPC)
    latest = None
    async for msg in client.iter_messages(chat_id, limit=1):
        latest = msg.date.strftime("%Y-%m-%d") if msg.date else None

    # Earliest message (1 RPC, with timeout protection for reverse=True bug)
    earliest = None
    try:
        async with asyncio.timeout(10.0):
            async for msg in client.iter_messages(chat_id, limit=1, reverse=True):
                earliest = msg.date.strftime("%Y-%m-%d") if msg.date else None
                break
    except TimeoutError:
        logger.debug("Earliest message lookup timed out for chat %d", chat_id)

    return {"earliest": earliest, "latest": latest, "total": total}


@router.get("/{account}/{chat_id}/message-dates")
async def message_dates(
    request: Request,
    account: AccountKey,
    chat_id: int,
    year: int,
    month: int,
):
    """Get dates with messages for a specific month (cached)."""
    import calendar

    from ..database import get_cached_message_dates, get_db, set_cached_message_dates

    sm = resolve_session_manager(request)
    client = sm.get_client(account)
    if not await sm.is_authorized(account):
        raise HTTPException(status_code=401, detail="Not logged in.")

    # Check cache first
    db = await get_db()
    try:
        cached = await get_cached_message_dates(db, account, chat_id, year, month)
        if cached is not None:
            return {"dates": cached}

        # Cache miss — scan messages for this month
        last_day = calendar.monthrange(year, month)[1]
        start = datetime(year, month, 1, tzinfo=UTC)
        end = datetime(year, month, last_day, 23, 59, 59, tzinfo=UTC)

        dates_set: set[str] = set()
        async for msg in client.iter_messages(chat_id, offset_date=end, limit=None):
            if msg.date and msg.date < start:
                break  # past the month boundary, stop
            if msg.date and start <= msg.date <= end and not msg.action:
                dates_set.add(msg.date.strftime("%Y-%m-%d"))

        dates = sorted(dates_set)
        await set_cached_message_dates(db, account, chat_id, year, month, dates)
        return {"dates": dates}
    finally:
        await db.close()


@router.get("/{account}/{chat_id}/info")
async def chat_info(request: Request, account: AccountKey, chat_id: int):
    """Get chat details (JSON)."""
    sm = resolve_session_manager(request)
    client = sm.get_client(account)
    if not await sm.is_authorized(account):
        raise HTTPException(status_code=401, detail="Not logged in.")
    entity = await client.get_entity(chat_id)
    title = getattr(entity, "title", None)
    if isinstance(entity, types.User):
        title = f"{entity.first_name or ''} {entity.last_name or ''}".strip()
    return {
        "id": chat_id,
        "title": title,
        "type": _classify_entity(entity),
    }
