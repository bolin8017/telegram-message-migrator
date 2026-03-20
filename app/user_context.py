"""UserContext registry — holds per-user state and maps session tokens to contexts."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


class RegistryFullError(Exception):
    """Raised when the global context limit is reached."""


class SessionLimitError(Exception):
    """Raised when the per-user session limit is reached."""


@dataclass
class UserContext:
    """Per-user state container.

    Holds references to Telethon clients, transfer engine, and other
    per-session objects.  Uses ``Any`` type hints to avoid circular imports;
    actual types are enforced at runtime by the components that set them.
    """

    user_id: int  # Telegram user ID (from Account A)
    session_token: str  # browser cookie value
    session_manager: Any = None  # will be SessionManager (avoid circular import)
    engine: Any = None  # will be TransferEngine | None
    live_forwarder: Any = None  # will be LiveForwarder | None
    rate_limiter: Any = None  # will be RateLimiter
    last_active: datetime = field(default_factory=lambda: datetime.now(UTC))
    api_id: int = 0  # decrypted, in-memory only
    api_hash: str = ""  # decrypted, in-memory only
    user_agent_hash: str | None = None  # SHA-256 of User-Agent at session creation
    ip_prefix: str | None = None  # network prefix of IP at session creation


# ---------------------------------------------------------------------------
# Global registry
# ---------------------------------------------------------------------------

_contexts: dict[str, UserContext] = {}  # session_token → UserContext
_user_sessions: dict[int, set[str]] = {}  # user_id → set of session_tokens


# ---------------------------------------------------------------------------
# Registry operations
# ---------------------------------------------------------------------------


def register_context(
    ctx: UserContext,
    *,
    max_contexts: int = 50,
    max_per_user: int = 3,
) -> None:
    """Add a context to the registry.

    Raises:
        RegistryFullError: If the global limit (*max_contexts*) is reached.
        SessionLimitError: If the per-user limit (*max_per_user*) is reached.
    """
    if len(_contexts) >= max_contexts:
        raise RegistryFullError(f"Global context limit reached ({max_contexts})")

    current_count = get_user_session_count(ctx.user_id)
    if current_count >= max_per_user:
        raise SessionLimitError(f"User {ctx.user_id} already has {current_count} sessions (max {max_per_user})")

    _contexts[ctx.session_token] = ctx
    _user_sessions.setdefault(ctx.user_id, set()).add(ctx.session_token)


def get_context(token: str) -> UserContext | None:
    """Look up a context by session token.  Returns ``None`` if not found."""
    return _contexts.get(token)


def get_user_session_count(user_id: int) -> int:
    """Return the number of active sessions for *user_id*."""
    return len(_user_sessions.get(user_id, set()))


def remove_context(token: str) -> None:
    """Remove a context from the registry.  No-op if *token* is not found."""
    ctx = _contexts.pop(token, None)
    if ctx is None:
        return

    tokens = _user_sessions.get(ctx.user_id)
    if tokens is not None:
        tokens.discard(token)
        if not tokens:
            del _user_sessions[ctx.user_id]


def get_all_contexts() -> dict[str, UserContext]:
    """Return a shallow copy of the registry for cleanup iteration."""
    return dict(_contexts)
