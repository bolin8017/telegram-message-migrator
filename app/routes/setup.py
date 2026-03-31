"""Setup routes — credential provisioning for multi-user mode."""

import hashlib
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from ..config import get_settings
from ..crypto import derive_key, encrypt
from ..database import create_user_session, get_db
from ..middleware import create_session_cookie, extract_ip_prefix, hash_token, hash_user_agent
from ..models import SetupCredentialsRequest
from ..rate_limiter import RateLimiter
from ..telegram_client import SessionManager
from ..user_context import (
    RegistryFullError,
    SessionLimitError,
    UserContext,
    register_context,
)

router = APIRouter(prefix="/api/setup", tags=["setup"])

# Reuse the limiter from auth routes
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)


@router.get("/mode")
async def get_setup_mode():
    """Return whether the server is in single-user or multi-user mode."""
    s = get_settings()
    return {"single_user_mode": s.single_user_mode}


@router.post("/credentials")
@limiter.limit("5/hour")
async def setup_credentials(request: Request, body: SetupCredentialsRequest):
    """Accept user-provided Telegram API credentials (multi-user only).

    Creates a session cookie, encrypts credentials, stores them in the DB,
    and registers a minimal UserContext in the in-memory registry.
    """
    s = get_settings()
    if s.single_user_mode:
        raise HTTPException(status_code=404, detail="Not available in single-user mode")

    # Create session token
    token = create_session_cookie()
    token_hash = hash_token(token)

    # Derive a per-session temporary user_id from the token hash.
    # This ensures each user gets a unique encryption key even before
    # Telegram login (when the real user_id is not yet known).
    # After login, credentials are re-encrypted with the real user_id.
    # Mask to 63 bits so the value fits in a signed SQLite INTEGER column
    temp_user_id = int.from_bytes(hashlib.sha256(token.encode()).digest()[:8], "big") & 0x7FFFFFFFFFFFFFFF

    key = derive_key(s.server_secret, temp_user_id)
    creds_blob = encrypt(
        json.dumps({"api_id": body.api_id, "api_hash": body.api_hash}).encode(),
        key,
    )

    # Capture session binding data
    ua_hash = hash_user_agent(request.headers.get("user-agent", ""))
    ip_pfx = extract_ip_prefix(request.client.host if request.client else "")

    # Store in DB
    db = await get_db()
    try:
        await create_user_session(
            db,
            user_id=temp_user_id,
            session_token_hash=token_hash,
            encrypted_session_a=None,
            encrypted_session_b=None,
            encrypted_credentials=creds_blob,
            encryption_version=1,
            user_agent_hash=ua_hash,
            ip_prefix=ip_pfx,
        )
    finally:
        await db.close()

    # Create a minimal UserContext with SessionManager
    sm = SessionManager(api_id=body.api_id, api_hash=body.api_hash)
    ctx = UserContext(
        user_id=temp_user_id,
        session_token=token,
        session_manager=sm,
        rate_limiter=RateLimiter(),
        api_id=body.api_id,
        api_hash=body.api_hash,
        user_agent_hash=ua_hash,
        ip_prefix=ip_pfx,
    )
    try:
        register_context(ctx, max_contexts=s.max_user_contexts, max_per_user=s.max_sessions_per_user)
    except (RegistryFullError, SessionLimitError) as e:
        raise HTTPException(status_code=503, detail=str(e))

    # Set session cookie in response
    response = JSONResponse({"status": "credentials_saved"})
    response.set_cookie(
        "session_id",
        token,
        httponly=True,
        samesite="strict",
        secure=not s.single_user_mode,  # secure in production
        max_age=s.session_expiry_days * 86400,
    )
    return response
