"""Transfer routes — JSON API for transfer jobs, progress, and history.

Supports both SINGLE_USER_MODE (global engine/session_manager on app.state) and
multi-user mode (per-user contexts via session_id cookie).
"""

import asyncio
import csv
import io
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from ..config import get_settings
from ..database import get_db, get_transfer_count, get_transfer_history
from ..middleware import resolve_session_manager
from ..models import TransferJobCreate
from ..telegram_client import AccountKey

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/transfer", tags=["transfer"])


# ── Mode-aware helpers ────────────────────────────────────────────────


def _get_engine(request: Request):
    """Get the user's TransferEngine based on mode.

    Raises HTTPException(400) if the engine is not available (e.g. session
    upgrade failed after login).
    """
    s = get_settings()
    if s.single_user_mode:
        engine = request.app.state.engine  # set in main.py lifespan
    else:
        token = request.cookies.get("session_id")
        if not token:
            raise HTTPException(401, "Not authenticated")
        from ..user_context import get_context

        ctx = get_context(token)
        if not ctx:
            raise HTTPException(401, "Session expired")
        engine = ctx.engine
    if engine is None:
        raise HTTPException(400, "Transfer engine not available. Please re-login.")
    return engine


# ── Job lifecycle ─────────────────────────────────────────────────────


@router.post("/jobs")
async def create_job(request: Request, config: TransferJobCreate):
    """Create and start a new transfer job."""
    sm = resolve_session_manager(request)
    from ..telegram_client import opposite_account

    source_account = config.source_account
    target_account = opposite_account(source_account)
    if not await sm.is_authorized(source_account):
        raise HTTPException(400, f"Source account ({source_account}) not logged in")
    if not await sm.is_authorized(target_account):
        raise HTTPException(400, f"Target account ({target_account}) not logged in")

    engine = _get_engine(request)

    try:
        job_id = await engine.start(config)
    except RuntimeError as e:
        raise HTTPException(409, str(e))

    return {"job_id": job_id}


@router.get("/progress/{job_id}")
async def progress_sse(request: Request, job_id: str):
    """SSE endpoint for real-time transfer progress."""
    engine = _get_engine(request)
    if not engine or engine.job_id != job_id:
        raise HTTPException(403, "Not your job")

    queue = engine.subscribe()

    async def event_stream():
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"event: {msg['type']}\ndata: {json.dumps(msg['data'])}\n\n"
                    if msg["type"] in ("job_completed", "job_failed", "job_cancelled"):
                        break
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            engine.unsubscribe(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/jobs/pause")
async def pause_job(request: Request):
    """Pause the running transfer."""
    engine = _get_engine(request)
    engine.pause()
    return {"status": "paused"}


@router.post("/jobs/resume")
async def resume_job(request: Request):
    """Resume a paused transfer."""
    engine = _get_engine(request)
    engine.resume()
    return {"status": "resumed"}


@router.post("/jobs/cancel")
async def cancel_job(request: Request):
    """Cancel the running transfer."""
    engine = _get_engine(request)
    engine.cancel()
    return {"status": "cancelled"}


@router.get("/status")
async def get_status(request: Request):
    """Get current engine status (JSON)."""
    engine = _get_engine(request)
    return {
        "job_id": engine.job_id,
        "status": engine.status.value if engine.status else "idle",
        "progress": engine.progress.model_dump() if engine.progress else None,
    }


# ── Estimation & target chats ────────────────────────────────────────


@router.get("/estimate-count")
async def estimate_count(
    request: Request,
    source_chat_id: int,
    source_account: AccountKey = "account_a",
    date_from: str = "",
    date_to: str = "",
):
    """Estimate message count for transfer confirmation preview."""
    from datetime import UTC, datetime

    sm = resolve_session_manager(request)

    try:
        authorized = await asyncio.wait_for(sm.is_authorized(source_account), timeout=5.0)
        if not authorized:
            return {"count": 0, "error": "Not logged in"}
    except Exception:
        return {"count": 0, "error": "Not logged in"}

    client = sm.get_client(source_account)
    try:
        total_obj = await client.get_messages(source_chat_id, limit=0)
    except ValueError:
        return {"count": 0, "error": "Invalid chat ID"}
    except Exception as e:
        logger.warning("Failed to get messages for chat %d: %s", source_chat_id, e)
        return {"count": 0, "error": "Failed to access chat"}
    total = total_obj.total if total_obj else 0

    # If date filters specified, do a rough count by sampling
    if date_from or date_to:
        dt_from = datetime.fromisoformat(date_from).replace(tzinfo=UTC) if date_from else None
        dt_to = datetime.fromisoformat(date_to).replace(tzinfo=UTC) if date_to else None
        count = 0
        async for msg in client.iter_messages(source_chat_id, reverse=True):
            if msg.action:
                continue
            if dt_from and msg.date and msg.date < dt_from:
                continue
            if dt_to and msg.date and msg.date > dt_to:
                break
            count += 1
            if count >= 10000:  # cap iteration for speed
                break
        return {"count": count, "total": total, "capped": count >= 10000}

    return {"count": total, "total": total, "capped": False}


@router.get("/target-chats")
async def target_chats(
    request: Request,
    target_account: AccountKey = "account_b",
):
    """List target account chats for target selection (JSON)."""
    from .chats import _dialog_to_chat

    sm = resolve_session_manager(request)
    if not await sm.is_authorized(target_account):
        raise HTTPException(400, f"Target account ({target_account}) not logged in")

    client = sm.get_client(target_account)
    chats = []
    async for dialog in client.iter_dialogs(limit=100):
        chats.append(_dialog_to_chat(dialog).model_dump())

    return {"chats": chats}


# ── History (SINGLE_USER_MODE only) ──────────────────────────────────


@router.get("/history")
async def transfer_history(request: Request, page: int = 1):
    """Show transfer history (only available in single-user mode)."""
    s = get_settings()
    if not s.single_user_mode:
        raise HTTPException(404, "History not available in multi-user mode")

    per_page = 20
    db = await get_db()
    try:
        total = await get_transfer_count(db)
        jobs = await get_transfer_history(db, limit=per_page, offset=(page - 1) * per_page)
    finally:
        await db.close()

    return {
        "jobs": jobs,
        "page": page,
        "total": total,
        "has_more": page * per_page < total,
    }


@router.get("/history/{job_id}/export")
async def export_job(request: Request, job_id: str, fmt: str = "csv"):
    """Export transfer message log as CSV or JSON (only available in single-user mode)."""
    s = get_settings()
    if not s.single_user_mode:
        raise HTTPException(404, "Export not available in multi-user mode")

    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT source_msg_id, dest_msg_id, status, error, created_at
               FROM messages WHERE transfer_id = ? ORDER BY source_msg_id""",
            (job_id,),
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()

    records = [dict(r) for r in rows]
    if fmt == "json":
        return Response(
            json.dumps(records, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="transfer_{job_id}.json"'},
        )

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["source_msg_id", "dest_msg_id", "status", "error", "created_at"])
    writer.writeheader()
    writer.writerows(records)
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="transfer_{job_id}.csv"'},
    )
