"""User routes — data management for multi-user mode."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from ..database import delete_user_session, get_db
from ..middleware import hash_token, require_multi_user
from ..user_context import UserContext, remove_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/user", tags=["user"])


@router.delete("/data")
async def delete_user_data(ctx: UserContext = Depends(require_multi_user)):
    """Delete all user data (7-step process from spec Section 2.8).

    Steps:
    1. Cancel active transfer
    2. Stop live forwarder
    3. Log out Telegram sessions
    4-5. Delete from DB
    6. Remove from in-memory registry
    7. Clear session cookie
    """
    token = ctx.session_token

    # Step 1: Cancel active transfer
    if ctx.engine and hasattr(ctx.engine, "cancel"):
        ctx.engine.cancel()

    # Step 2: Stop live forwarder
    if ctx.live_forwarder and hasattr(ctx.live_forwarder, "stop"):
        await ctx.live_forwarder.stop()

    # Step 2.5: Delete relay group
    if ctx.session_manager and hasattr(ctx.session_manager, "delete_relay_group"):
        try:
            await ctx.session_manager.delete_relay_group()
        except Exception:
            logger.warning("Failed to delete relay group during user data deletion", exc_info=True)

    # Step 3: Log out Telegram sessions
    if ctx.session_manager:
        for account in ("account_a", "account_b"):
            try:
                if await ctx.session_manager.is_authorized(account):
                    client = ctx.session_manager.get_client(account)
                    await client.log_out()
            except Exception:
                logger.warning("Failed to log out %s during user data deletion", account, exc_info=True)
        await ctx.session_manager.disconnect_all()

    # Step 4-5: Delete from DB
    db = await get_db()
    try:
        await delete_user_session(db, hash_token(token))
    finally:
        await db.close()

    # Step 6: Remove from registry
    remove_context(token)

    # Step 7: Clear cookie
    response = JSONResponse({"status": "deleted"})
    response.delete_cookie("session_id")
    return response


@router.get("/relay-group")
async def get_relay_group_status(ctx: UserContext = Depends(require_multi_user)):
    """Return relay group status for current user."""
    token = ctx.session_token

    if ctx.session_manager and ctx.session_manager.relay_group_id:
        db = await get_db()
        try:
            from ..database import get_relay_group as get_relay_group_record

            record = await get_relay_group_record(db, hash_token(token))
        finally:
            await db.close()

        return {
            "exists": True,
            "group_id": ctx.session_manager.relay_group_id,
            "created_at": record["created_at"] if record else None,
        }

    return {"exists": False, "group_id": None, "created_at": None}


@router.delete("/relay-group")
async def delete_relay_group_endpoint(ctx: UserContext = Depends(require_multi_user)):
    """Delete the relay group entirely."""
    token = ctx.session_token

    if not ctx.session_manager or not ctx.session_manager.relay_group_id:
        raise HTTPException(status_code=404, detail="No relay group exists")

    db = await get_db()
    try:
        await ctx.session_manager.delete_relay_group(db=db, user_token=hash_token(token))
    finally:
        await db.close()

    return {"status": "deleted"}


@router.delete("/relay-group/messages")
async def clear_relay_group_messages(ctx: UserContext = Depends(require_multi_user)):
    """Delete all messages in the relay group (capped at 1000)."""
    sm = ctx.session_manager
    if not sm or not sm.relay_group_id or not sm.relay_entity_a:
        raise HTTPException(status_code=404, detail="No relay group exists")

    source = sm.get_client("account_a")
    if not source:
        raise HTTPException(status_code=500, detail="Account A not connected")

    deleted = 0
    batch = []
    async for msg in source.iter_messages(sm.relay_entity_a, limit=1000):
        batch.append(msg.id)
        if len(batch) >= 100:
            await sm.cleanup_relay_messages(batch)
            deleted += len(batch)
            batch.clear()
    if batch:
        await sm.cleanup_relay_messages(batch)
        deleted += len(batch)

    return {"status": "cleared", "deleted": deleted}
