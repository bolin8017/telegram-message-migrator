"""Auth routes — JSON API for Telegram login flow.

Supports both SINGLE_USER_MODE (global SessionManager on app.state) and
multi-user mode (per-user contexts via pending_token during auth).
"""

import json
import logging
import secrets
import time
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from telethon import TelegramClient, errors

from ..config import get_settings
from ..models import (
    AccountInfo,
    AuthStatusResponse,
    SendCodeRequest,
    Submit2FARequest,
    SubmitCodeRequest,
)
from ..telegram_client import AccountKey, SessionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

limiter = Limiter(key_func=get_remote_address)


# ── Pending auth state (server-side phone_code_hash storage) ──────────


@dataclass
class PendingAuth:
    """Temporary state held between send-code and submit-code steps."""

    phone: str
    phone_code_hash: str
    client: TelegramClient
    account: AccountKey
    created_at: float


# pending_token → PendingAuth
# Entries have a 15-minute TTL; expired entries cleaned by _cleanup_loop (main.py).
_pending_auths: dict[str, PendingAuth] = {}

_PENDING_TTL_SECONDS = 15 * 60  # 15 minutes


# ── Helper: resolve SessionManager based on mode ─────────────────────


def _get_session_manager(request: Request) -> SessionManager | None:
    """Return the appropriate SessionManager based on operating mode.

    In SINGLE_USER_MODE the global SessionManager lives on app.state.
    In multi-user mode returns None — callers use the pending auth client
    directly (the user may not have a UserContext yet during auth).
    """
    s = get_settings()
    if s.single_user_mode:
        return request.app.state.session_manager
    return None


# ── Session upgrade after successful login (multi-user) ───────────────


async def _upgrade_session_after_login(
    request: Request,
    client: TelegramClient,
    account: AccountKey,
) -> None:
    """Upgrade the UserContext after successful Telegram login.

    1. Get real user_id from Telegram.
    2. Re-encrypt credentials + session blob with the real user_id as HKDF salt.
    3. Update DB record with real user_id and re-encrypted data.
    4. Update in-memory UserContext with engine and live forwarder.
    """
    from ..crypto import derive_key, encrypt
    from ..database import get_db, upgrade_session_user_id
    from ..live_forwarder import LiveForwarder
    from ..middleware import hash_token
    from ..rate_limiter import RateLimiter
    from ..transfer_engine import TransferEngine
    from ..user_context import get_context

    s = get_settings()

    # Look up existing UserContext from the session_id cookie
    session_token = request.cookies.get("session_id")
    if not session_token:
        logger.warning("No session_id cookie found after login — skipping session upgrade")
        return

    ctx = get_context(session_token)
    if ctx is None:
        logger.warning("No UserContext found for session — skipping session upgrade")
        return

    # Get real Telegram user info
    me = await client.get_me()
    user_id = me.id

    # Re-encrypt credentials with the real user_id
    token_hash = hash_token(session_token)
    key = derive_key(s.server_secret, user_id)
    creds_blob = encrypt(
        json.dumps({"api_id": ctx.api_id, "api_hash": ctx.api_hash}).encode(),
        key,
    )

    # Encrypt the authenticated StringSession
    session_str = None
    if hasattr(client.session, "save"):
        session_str = client.session.save()

    encrypted_session = None
    if session_str:
        encrypted_session = encrypt(session_str.encode(), key)

    # Update DB: real user_id + re-encrypted data
    db = await get_db()
    try:
        if account == "account_a":
            kwargs = {"encrypted_session_a": encrypted_session}
        else:
            kwargs = {"encrypted_session_b": encrypted_session}
        await upgrade_session_user_id(
            db,
            token_hash,
            new_user_id=user_id,
            encrypted_credentials=creds_blob,
            **kwargs,
        )
    finally:
        await db.close()

    # Update in-memory UserContext
    ctx.user_id = user_id

    # Attach the client's SessionManager to the context if it doesn't
    # already have one with this account connected
    if ctx.session_manager is not None:
        sm = ctx.session_manager
        # Register the authenticated client in the SessionManager
        sm.set_client(account, client)
    else:
        sm = SessionManager(api_id=ctx.api_id, api_hash=ctx.api_hash)
        sm.set_client(account, client)
        ctx.session_manager = sm

    # Create TransferEngine and LiveForwarder
    semaphore = request.app.state.semaphore if hasattr(request.app.state, "semaphore") else None
    ctx.engine = TransferEngine(
        session_manager=ctx.session_manager,
        semaphore=semaphore,
        max_messages=s.max_messages_per_job,
        persist_checkpoints=False,  # multi-user: RAM only
    )
    ctx.live_forwarder = LiveForwarder(session_manager=ctx.session_manager)

    if ctx.rate_limiter is None:
        ctx.rate_limiter = RateLimiter()

    logger.info("Session upgraded for user %d (account %s)", user_id, account)


# ── Routes ────────────────────────────────────────────────────────────


@router.get("/status", response_model=AuthStatusResponse)
async def get_auth_status(request: Request):
    """Return authorization status for both accounts."""
    s = get_settings()
    result: dict = {"account_a": None, "account_b": None}

    if s.single_user_mode:
        sm = request.app.state.session_manager
    else:
        # Multi-user: resolve SessionManager from UserContext via session cookie.
        # Return empty result (not 401) if no session — the onboarding wizard
        # calls this endpoint to detect whether the user is already logged in.
        from ..user_context import get_context

        token = request.cookies.get("session_id")
        ctx = get_context(token) if token else None
        sm = ctx.session_manager if ctx else None

    if sm is not None:
        for account in ("account_a", "account_b"):
            try:
                info = await sm.get_user_info(account)
                if info:
                    result[account] = AccountInfo(**info)
            except Exception:
                # Connection or auth check failed — treat as not logged in
                logger.warning("Failed to check auth for %s", account, exc_info=True)

    return AuthStatusResponse(**result)


@router.post("/send-code/{account}")
@limiter.limit("3/10minutes")
async def send_code(request: Request, account: AccountKey, body: SendCodeRequest):
    """Send a verification code to the given phone number.

    Stores the phone_code_hash server-side (never exposed to the client)
    and sets a ``pending_token`` cookie for subsequent submit-code calls.
    """
    phone = body.phone.strip()
    if not phone:
        raise HTTPException(status_code=422, detail="Phone number is required")

    # Prevent concurrent login flows for the same phone number
    for pa in _pending_auths.values():
        if pa.phone == phone:
            raise HTTPException(
                status_code=409,
                detail="Login already in progress for this phone number",
            )

    sm = _get_session_manager(request)

    if sm is not None:
        # SINGLE_USER_MODE — use the global SessionManager's client
        client = sm.get_client(account)
    else:
        # Multi-user mode — create a temporary client for the auth flow.
        # Reuse existing pending client if the user already started a flow.
        existing_token = request.cookies.get("pending_token")
        if existing_token and existing_token in _pending_auths:
            client = _pending_auths[existing_token].client
        else:
            s = get_settings()
            if not s.telegram_api_id or not s.telegram_api_hash:
                raise HTTPException(
                    status_code=500,
                    detail="Telegram API credentials not configured",
                )
            temp_sm = SessionManager(api_id=s.telegram_api_id, api_hash=s.telegram_api_hash)
            client = temp_sm.get_client(account)

    try:
        if not client.is_connected():
            await client.connect()
    except Exception as e:
        logger.warning("Failed to connect to Telegram for %s: %s", account, e)
        raise HTTPException(status_code=502, detail="Cannot connect to Telegram. Please try again.")

    try:
        sent = await client.send_code_request(phone)
    except errors.PhoneNumberInvalidError:
        raise HTTPException(status_code=422, detail="Invalid phone number")
    except errors.FloodWaitError as e:
        return JSONResponse(
            {"detail": "Rate limited", "wait_seconds": e.seconds},
            status_code=429,
        )
    except Exception as e:
        logger.warning("Failed to send code for %s: %s", account, e)
        raise HTTPException(status_code=502, detail="Failed to send code. Please try again.")

    # Store pending auth server-side
    pending_token = secrets.token_urlsafe(32)
    _pending_auths[pending_token] = PendingAuth(
        phone=phone,
        phone_code_hash=sent.phone_code_hash,
        client=client,
        account=account,
        created_at=time.time(),
    )

    response = JSONResponse({"status": "code_sent"})
    response.set_cookie(
        "pending_token",
        pending_token,
        httponly=True,
        samesite="strict",
        secure=not get_settings().single_user_mode,
        max_age=_PENDING_TTL_SECONDS,
    )
    return response


def _get_pending_auth(request: Request) -> PendingAuth:
    """Resolve PendingAuth from the pending_token cookie.

    Raises HTTPException(400) if the token is missing or expired.
    """
    token = request.cookies.get("pending_token")
    if not token or token not in _pending_auths:
        raise HTTPException(
            status_code=400,
            detail="No pending auth session. Please send a code first.",
        )
    pa = _pending_auths[token]
    if time.time() - pa.created_at > _PENDING_TTL_SECONDS:
        del _pending_auths[token]
        raise HTTPException(status_code=400, detail="Auth session expired. Please send a new code.")
    return pa


async def _finalize_login(
    request: Request,
    sm: SessionManager | None,
    client: TelegramClient,
    account: AccountKey,
) -> JSONResponse:
    """Shared post-login logic for submit_code and submit_2fa.

    Fetches user info, upgrades session (multi-user), cleans up pending auth,
    and returns the success response.
    """
    info = None
    upgrade_warning = None
    if sm is not None:
        try:
            info = await sm.get_user_info(account)
        except Exception:
            logger.warning("Failed to get user info for %s after login", account, exc_info=True)
    else:
        me = await client.get_me()
        info = {
            "phone": me.phone or "",
            "name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
            "username": me.username,
        }
        try:
            await _upgrade_session_after_login(request, client, account)
        except Exception:
            logger.exception("Failed to upgrade session after login")
            upgrade_warning = "Session setup incomplete. Some features may not work until you re-login."

    # Clean up pending auth
    token = request.cookies.get("pending_token")
    if token and token in _pending_auths:
        del _pending_auths[token]

    user_info = AccountInfo(**info) if info else None
    result: dict = {"status": "success", "user": user_info.model_dump() if user_info else None}
    if upgrade_warning:
        result["warning"] = upgrade_warning
    response = JSONResponse(result)
    response.delete_cookie("pending_token")
    return response


@router.post("/submit-code/{account}")
@limiter.limit("5/5minutes")
async def submit_code(request: Request, account: AccountKey, body: SubmitCodeRequest):
    """Submit verification code to complete sign-in.

    Reads phone and phone_code_hash from the server-side pending auth state.
    """
    code = body.code.strip()
    if not code:
        raise HTTPException(status_code=422, detail="Verification code is required")

    sm = _get_session_manager(request)
    pa = _get_pending_auth(request)
    client = sm.get_client(account) if sm is not None else pa.client

    if pa.account != account:
        raise HTTPException(
            status_code=400,
            detail=f"Pending auth is for {pa.account}, not {account}",
        )

    try:
        await client.sign_in(pa.phone, code, phone_code_hash=pa.phone_code_hash)
    except errors.SessionPasswordNeededError:
        return JSONResponse({"status": "2fa_required"})
    except errors.PhoneCodeInvalidError:
        raise HTTPException(status_code=422, detail="Invalid verification code")
    except errors.PhoneCodeExpiredError:
        token = request.cookies.get("pending_token")
        if token and token in _pending_auths:
            del _pending_auths[token]
        raise HTTPException(status_code=422, detail="Code expired. Please request a new one.")
    except errors.FloodWaitError as e:
        return JSONResponse(
            {"detail": "Rate limited", "wait_seconds": e.seconds},
            status_code=429,
        )

    return await _finalize_login(request, sm, client, account)


@router.post("/submit-2fa/{account}")
@limiter.limit("3/10minutes")
async def submit_2fa(request: Request, account: AccountKey, body: Submit2FARequest):
    """Submit 2FA password to complete sign-in."""
    password = body.password.strip()
    if not password:
        raise HTTPException(status_code=422, detail="2FA password is required")

    sm = _get_session_manager(request)
    pa = _get_pending_auth(request)
    client = sm.get_client(account) if sm is not None else pa.client

    if pa.account != account:
        raise HTTPException(
            status_code=400,
            detail=f"Pending auth is for {pa.account}, not {account}",
        )

    try:
        await client.sign_in(password=password)
    except errors.PasswordHashInvalidError:
        raise HTTPException(status_code=422, detail="Incorrect 2FA password")
    except errors.FloodWaitError as e:
        return JSONResponse(
            {"detail": "Rate limited", "wait_seconds": e.seconds},
            status_code=429,
        )

    return await _finalize_login(request, sm, client, account)


@router.post("/logout/{account}")
async def logout(request: Request, account: AccountKey):
    """Log out and delete session for the specified account."""
    sm = _get_session_manager(request)
    if sm is not None:
        # SINGLE_USER_MODE
        if await sm.is_authorized(account):
            client = sm.get_client(account)
            await client.log_out()
    else:
        # Multi-user mode: resolve from UserContext
        from ..user_context import get_context

        token = request.cookies.get("session_id")
        ctx = get_context(token) if token else None
        if ctx and ctx.session_manager:
            if await ctx.session_manager.is_authorized(account):
                client = ctx.session_manager.get_client(account)
                await client.log_out()
    return {"status": "ok"}
