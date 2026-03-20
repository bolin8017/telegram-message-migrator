"""Session cookie middleware — glue between HTTP requests and UserContext."""

import hashlib
import logging
import secrets
from datetime import UTC, datetime

from fastapi import HTTPException, Request

from .user_context import UserContext, get_context, register_context

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


def create_session_cookie() -> str:
    """Generate a cryptographically secure session token (URL-safe, 32 bytes)."""
    return secrets.token_urlsafe(32)


def _sha256_hex(value: str) -> str:
    """SHA-256 hex digest of a string value."""
    return hashlib.sha256(value.encode()).hexdigest()


hash_token = _sha256_hex
"""SHA-256 hash a raw token for safe DB storage (never store raw tokens)."""

hash_user_agent = _sha256_hex
"""SHA-256 hash of User-Agent string for session binding."""


def extract_ip_prefix(ip: str) -> str:
    """Extract network prefix from an IP address (first 3 octets IPv4, first 4 groups IPv6)."""
    if ":" in ip:
        return ":".join(ip.split(":")[:4])
    return ".".join(ip.split(".")[:3])


# ---------------------------------------------------------------------------
# Mode-aware SessionManager resolver (shared by transfer & live routes)
# ---------------------------------------------------------------------------


def resolve_session_manager(request: Request):
    """Return the user's SessionManager based on operating mode.

    In SINGLE_USER_MODE the global SessionManager lives on ``app.state``.
    In multi-user mode the SessionManager is retrieved from the user's context
    via the ``session_id`` cookie.

    Raises:
        HTTPException(401): If no valid session is found in multi-user mode.
    """
    from .config import get_settings

    s = get_settings()
    if s.single_user_mode:
        return request.app.state.session_manager
    token = request.cookies.get("session_id")
    ctx = get_context(token) if token else None
    if not ctx:
        raise HTTPException(401, "Not authenticated")
    if ctx.session_manager is None:
        raise HTTPException(400, "Session incomplete. Please complete login.")
    return ctx.session_manager


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def require_multi_user(request: Request) -> UserContext:
    """FastAPI dependency — require multi-user mode and a valid session.

    Raises:
        HTTPException(404): If running in single-user mode.
        HTTPException(401): If no valid session (delegated to ``require_user``).
    """
    from .config import get_settings

    if get_settings().single_user_mode:
        raise HTTPException(404, "Not available in single-user mode")
    return await require_user(request)


async def require_user(request: Request) -> UserContext:
    """FastAPI dependency — resolve the current user from the session cookie.

    Usage::

        @router.get("/protected")
        async def protected(ctx: UserContext = Depends(require_user)):
            ...

    Raises:
        HTTPException(401): If no cookie, or session cannot be found/rebuilt.
    """
    token = request.cookies.get("session_id")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Fast path: context is already in the in-memory registry
    ctx = get_context(token)
    if ctx is not None:
        # Validate session binding (UA + IP) if stored
        if ctx.user_agent_hash and ctx.ip_prefix:
            current_ua = hash_user_agent(request.headers.get("user-agent", ""))
            current_ip = extract_ip_prefix(request.client.host if request.client else "")
            if not validate_session_binding(ctx.user_agent_hash, ctx.ip_prefix, current_ua, current_ip):
                logger.warning("Session binding mismatch for user %d — both UA and IP changed", ctx.user_id)
                raise HTTPException(status_code=401, detail="Session binding changed. Please re-login.")
        ctx.last_active = datetime.now(UTC)
        return ctx

    # Slow path: server may have restarted — try to rebuild from DB
    ctx = await _rebuild_user_context(token)
    if ctx is None:
        raise HTTPException(status_code=401, detail="Session expired")

    return ctx


# ---------------------------------------------------------------------------
# Session binding validation
# ---------------------------------------------------------------------------


def validate_session_binding(
    stored_ua: str,
    stored_ip: str,
    current_ua: str,
    current_ip: str,
) -> bool:
    """Check whether a session's binding (UA + IP) is still acceptable.

    Policy:
    - Both UA **and** IP changed  ->  False  (require re-auth)
    - Only one changed           ->  True   (common on mobile networks)
    - Neither changed            ->  True
    """
    ua_changed = stored_ua != current_ua
    ip_changed = stored_ip != current_ip
    if ua_changed and ip_changed:
        return False
    return True


# ---------------------------------------------------------------------------
# Context rebuild (after server restart)
# ---------------------------------------------------------------------------


async def _rebuild_user_context(token: str) -> UserContext | None:
    """Attempt to rebuild a UserContext from a persisted DB session.

    Steps:
    1. Hash token -> look up ``user_sessions`` row in DB.
    2. Derive encryption key from ``server_secret`` + ``user_id``.
    3. Decrypt StringSession blobs and credentials.
    4. Reconnect Telethon client and verify ``is_user_authorized()``.
    5. Register rebuilt context in the in-memory registry.

    Returns ``None`` on any failure (defensive).
    """
    try:
        from .config import get_settings
        from .crypto import CryptoError, decrypt, derive_key
        from .database import get_db, get_user_session

        token_hash = hash_token(token)
        db = await get_db()
        try:
            row = await get_user_session(db, token_hash)
        finally:
            await db.close()

        if row is None:
            return None

        user_id: int = row["user_id"]
        settings = get_settings()

        if not settings.server_secret:
            logger.error("Cannot rebuild session: server_secret not configured")
            return None

        key = derive_key(settings.server_secret, user_id, version=row["encryption_version"])

        # Decrypt credentials (api_id, api_hash)
        api_id = 0
        api_hash = ""
        if row["encrypted_credentials"]:
            try:
                import json

                creds_json = decrypt(row["encrypted_credentials"], key)
                creds = json.loads(creds_json)
                api_id = creds.get("api_id", 0)
                api_hash = creds.get("api_hash", "")
            except (CryptoError, json.JSONDecodeError) as exc:
                logger.warning("Failed to decrypt credentials for user %d: %s", user_id, exc)
                return None

        # Decrypt StringSession blobs
        _session_a_str: str | None = None
        _session_b_str: str | None = None
        if row["encrypted_session_a"]:
            try:
                _session_a_str = decrypt(row["encrypted_session_a"], key).decode()
            except CryptoError as exc:
                logger.warning("Failed to decrypt session_a for user %d: %s", user_id, exc)
                return None

        if row["encrypted_session_b"]:
            try:
                _session_b_str = decrypt(row["encrypted_session_b"], key).decode()
            except CryptoError as exc:
                logger.warning("Failed to decrypt session_b for user %d: %s", user_id, exc)
                return None

        # Reconnect Telethon clients using StringSession and verify auth
        if not api_id or not api_hash:
            logger.warning("Cannot rebuild session for user %d: missing credentials", user_id)
            return None

        from .rate_limiter import RateLimiter
        from .telegram_client import SessionManager

        sm = SessionManager(api_id=api_id, api_hash=api_hash)

        # Reconnect each account that has a saved session blob
        for account, session_str in [("account_a", _session_a_str), ("account_b", _session_b_str)]:
            if session_str is None:
                continue
            try:
                client = sm.get_client(account, session_string=session_str)
                await client.connect()
                if not await client.is_user_authorized():
                    logger.warning(
                        "Session for user %d account %s is no longer authorized",
                        user_id,
                        account,
                    )
                    # Session invalid — delete DB records and bail
                    db = await get_db()
                    try:
                        from .database import delete_user_session

                        await delete_user_session(db, token_hash)
                    finally:
                        await db.close()
                    # Clean up any already-connected clients
                    try:
                        await sm.disconnect_all()
                    except Exception:
                        logger.debug("Cleanup disconnect failed for user %d", user_id, exc_info=True)
                    return None
            except Exception:
                logger.exception("Failed to reconnect account %s for user %d", account, user_id)
                # Clean up any already-connected clients
                try:
                    await sm.disconnect_all()
                except Exception:
                    logger.debug("Cleanup disconnect failed for user %d", user_id, exc_info=True)
                return None

        ctx = UserContext(
            user_id=user_id,
            session_token=token,
            session_manager=sm,
            rate_limiter=RateLimiter(),
            api_id=api_id,
            api_hash=api_hash,
            user_agent_hash=row["user_agent_hash"],
            ip_prefix=row["ip_prefix"],
        )
        register_context(ctx)
        logger.info("Rebuilt user context for user %d from DB", user_id)
        return ctx

    except Exception:
        logger.exception("Unexpected error rebuilding user context")
        return None
