"""Live forwarding routes — JSON API for live mode with user-scoped forwarder access.

Supports both SINGLE_USER_MODE (global live_forwarder/session_manager on app.state) and
multi-user mode (per-user contexts via session_id cookie).
"""

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..config import get_settings
from ..middleware import resolve_session_manager
from ..models import LiveForwardStart

router = APIRouter(prefix="/api/live", tags=["live"])

_LIVE_EVENTS = frozenset(
    {
        "forwarded",
        "skipped",
        "failed",
        "live_stopped",
        "stats",
    }
)


# ── Mode-aware helpers ────────────────────────────────────────────────


def _get_live_forwarder(request: Request):
    """Get the user's LiveForwarder based on mode.

    Raises HTTPException(400) if the forwarder is not available.
    """
    s = get_settings()
    if s.single_user_mode:
        lf = request.app.state.live_forwarder
    else:
        token = request.cookies.get("session_id")
        if not token:
            raise HTTPException(401, "Not authenticated")
        from ..user_context import get_context

        ctx = get_context(token)
        if not ctx:
            raise HTTPException(401, "Session expired")
        lf = ctx.live_forwarder
    if lf is None:
        raise HTTPException(400, "Live forwarder not available. Please re-login.")
    return lf


# ── Live forwarding lifecycle ─────────────────────────────────────────


@router.post("/start")
async def start_live(request: Request, config: LiveForwardStart):
    """Start live forwarding."""
    sm = resolve_session_manager(request)
    if not await sm.is_authorized("account_a"):
        raise HTTPException(400, "Account A not logged in")
    if not await sm.is_authorized("account_b"):
        raise HTTPException(400, "Account B not logged in")

    lf = _get_live_forwarder(request)
    try:
        await lf.start(
            source_chat_id=config.source_chat_id,
            mode=config.mode,
            target_type=config.target_type,
            target_chat_id=config.target_chat_id,
            include_text=config.include_text,
            include_media=config.include_media,
            keyword_whitelist=config.keyword_whitelist,
            keyword_blacklist=config.keyword_blacklist,
        )
    except RuntimeError as e:
        raise HTTPException(409, str(e))

    return {"status": "started", "source_chat_id": config.source_chat_id, "mode": lf.mode}


@router.post("/stop")
async def stop_live(request: Request):
    """Stop live forwarding."""
    lf = _get_live_forwarder(request)
    await lf.stop()
    return {"status": "stopped", "stats": lf.stats}


@router.get("/status")
async def live_status(request: Request):
    """Get live forwarder status."""
    lf = _get_live_forwarder(request)
    return {
        "active": lf.active,
        "source_chat_id": lf.source_chat_id,
        "mode": lf.mode,
        "stats": lf.stats,
    }


@router.get("/events")
async def live_events(request: Request):
    """SSE stream of live forwarding events."""
    lf = _get_live_forwarder(request)
    queue = lf.subscribe()

    async def event_stream():
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30.0)
                    event_type = msg["type"]
                    if event_type not in _LIVE_EVENTS:
                        continue
                    yield f"event: {event_type}\ndata: {json.dumps(msg['data'])}\n\n"
                    if event_type == "live_stopped":
                        break
                except TimeoutError:
                    yield ": keepalive\n\n"
                    if not lf.active:
                        break
        finally:
            lf.unsubscribe(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
