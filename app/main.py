import asyncio
import logging
import logging.handlers
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .config import get_settings, init_settings, validate_settings_for_mode
from .database import init_db
from .routes import auth, chats, live, transfer
from .routes import setup as setup_routes
from .routes import user as user_routes


def _setup_logging() -> None:
    """Configure structured logging with optional file output."""
    s = get_settings()
    fmt = "%(asctime)s %(levelname)-8s %(name)s  %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if s.log_file:
        s.log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.handlers.RotatingFileHandler(s.log_file, maxBytes=10_000_000, backupCount=3))
    logging.basicConfig(level=s.log_level.upper(), format=fmt, handlers=handlers, force=True)
    # Quiet noisy libraries
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)


async def _cleanup_loop(settings) -> None:
    """Background task: expire inactive sessions, clean up pending auths."""
    from .database import cleanup_expired_sessions, get_db
    from .routes.auth import _pending_auths
    from .user_context import get_all_contexts, remove_context

    while True:
        try:
            await asyncio.sleep(60)  # run every 60 seconds

            now = time.time()

            # Clean expired pending auths (>15 min)
            expired_tokens = [tok for tok, pa in _pending_auths.items() if now - pa.created_at > 900]
            for tok in expired_tokens:
                pa = _pending_auths.pop(tok, None)
                if pa and pa.client and pa.client.is_connected():
                    try:
                        await pa.client.disconnect()
                    except Exception:
                        logging.getLogger(__name__).debug("Failed to disconnect pending auth client", exc_info=True)

            # Clean expired user sessions from DB
            db = await get_db()
            try:
                deleted = await cleanup_expired_sessions(db, settings.session_expiry_days)
                if deleted:
                    logging.getLogger(__name__).info("Cleaned up %d expired sessions", deleted)
            finally:
                await db.close()

            # Clean UserContexts whose sessions were deleted
            # (contexts in memory but no longer in DB)
            for token, ctx in list(get_all_contexts().items()):
                days_inactive = (datetime.now(UTC) - ctx.last_active).days
                if days_inactive >= settings.session_expiry_days:
                    if ctx.session_manager:
                        await ctx.session_manager.disconnect_all()
                    remove_context(token)

        except asyncio.CancelledError:
            raise
        except Exception:
            logging.getLogger(__name__).exception("Cleanup loop error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_settings()
    s = get_settings()
    validate_settings_for_mode(s)  # fail fast on bad config
    _setup_logging()
    await init_db()

    if s.single_user_mode:
        # SINGLE_USER_MODE: preserve current behavior exactly
        from .live_forwarder import LiveForwarder
        from .telegram_client import SessionManager
        from .transfer_engine import TransferEngine

        sm = SessionManager(
            api_id=s.telegram_api_id,
            api_hash=s.telegram_api_hash,
            session_dir=s.session_dir,
        )
        await sm.connect_all()
        app.state.session_manager = sm
        app.state.engine = TransferEngine(session_manager=sm)
        app.state.live_forwarder = LiveForwarder(session_manager=sm)
    else:
        # Multi-user mode: initialize semaphore and cleanup task
        app.state.semaphore = asyncio.Semaphore(s.max_concurrent_jobs)
        app.state.cleanup_task = asyncio.create_task(_cleanup_loop(s))

    logging.getLogger(__name__).info(
        "Application started (mode=%s)",
        "single-user" if s.single_user_mode else "multi-user",
    )
    yield

    # Shutdown
    if s.single_user_mode:
        await app.state.session_manager.disconnect_all()
    else:
        app.state.cleanup_task.cancel()
        try:
            await app.state.cleanup_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Telegram Message Migrator", lifespan=lifespan)

# Rate limiting
app.state.limiter = auth.limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Static files
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Routers
app.include_router(auth.router)
app.include_router(chats.router)
app.include_router(transfer.router)
app.include_router(live.router)
app.include_router(setup_routes.router)
app.include_router(user_routes.router)


@app.get("/health")
async def health():
    """Health check endpoint for Docker / monitoring."""
    return {"status": "ok"}


# SPA static files (production build)
dist_dir = Path(__file__).parent / "static" / "dist"
if dist_dir.exists():
    # Serve built assets (JS, CSS, images) from dist/assets/
    app.mount("/assets", StaticFiles(directory=dist_dir / "assets"), name="spa-assets")

    # Catch-all: serve index.html for any unmatched GET route (SPA client-side routing)
    @app.get("/{full_path:path}", response_class=HTMLResponse)
    async def spa_fallback(request: Request, full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail=f"API endpoint not found: /{full_path}")
        return FileResponse(dist_dir / "index.html")
else:
    # Development fallback when frontend isn't built
    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return HTMLResponse(
            "<html><body>"
            "<h1>Telegram Message Migrator</h1>"
            "<p>API is running. Build the frontend with: cd frontend &amp;&amp; npm run build</p>"
            "</body></html>"
        )
