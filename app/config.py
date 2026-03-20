from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Operating mode
    single_user_mode: bool = False

    # Telegram API (required in single-user mode, optional in multi-user)
    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None

    # Security
    server_secret: str | None = None

    # App
    log_level: str = "INFO"
    log_file: Path | None = None

    # Multi-user limits
    max_user_contexts: int = 50
    max_concurrent_jobs: int = 10
    max_messages_per_job: int = 50000
    session_expiry_days: int = 7
    max_sessions_per_user: int = 3

    # Paths
    session_dir: Path = Path("./sessions")
    db_path: Path = Path("./data.db")

    # Rate limiting – Forward mode
    forward_base_delay: float = 3.0
    forward_jitter: float = 0.4
    forward_burst: int = 2

    # Rate limiting – Copy text
    copy_text_base_delay: float = 3.5
    copy_text_jitter: float = 0.4
    copy_text_burst: int = 2

    # Rate limiting – Copy file
    copy_file_base_delay: float = 5.0
    copy_file_jitter: float = 0.3
    copy_file_burst: int = 1

    # Rate limiting – Read
    read_base_delay: float = 0.5
    read_jitter: float = 0.3
    read_burst: int = 5

    # Batch cooldown
    batch_size: int = 20
    batch_cooldown: float = 15.0
    batch_cooldown_jitter: float = 0.5

    # Long pause
    long_pause_interval: int = 100
    long_pause_min: float = 60.0
    long_pause_max: float = 180.0

    # Daily cap
    daily_message_cap: int = 1500

    # FloodWait handling
    flood_sleep_threshold: int = 60
    flood_rate_reduction: float = 0.5
    flood_min_rate: float = 0.05
    flood_extra_buffer: float = 1.2
    flood_auto_pause_count: int = 2
    flood_auto_pause_window: int = 1800

    # Recovery
    recovery_interval: int = 600
    recovery_factor: float = 1.15

    # Account age multiplier
    new_account_days: int = 30
    new_account_multiplier: float = 2.0
    medium_account_days: int = 90
    medium_account_multiplier: float = 1.5

    # Relay group forwarding
    relay_forward_base_delay: float = 4.0
    live_relay_cleanup_threshold: int = 10
    relay_group_title: str = "TMM Relay"

    # Telethon client
    request_retries: int = 3
    connection_retries: int = 3

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def init_settings() -> Settings:
    return get_settings()


def validate_settings_for_mode(s: Settings) -> None:
    """Validate settings based on operating mode. Called in lifespan, NOT at import."""
    import sys

    errors = []
    if s.single_user_mode:
        if not s.telegram_api_id or not s.telegram_api_hash:
            errors.append("SINGLE_USER_MODE requires TELEGRAM_API_ID and TELEGRAM_API_HASH in .env")
    else:
        if not s.server_secret or len(s.server_secret) < 32:
            errors.append(
                "SERVER_SECRET is required (>= 32 chars). "
                'Generate: python -c "import secrets; print(secrets.token_urlsafe(32))"'
            )
    if errors:
        for e in errors:
            print(f"[CONFIG ERROR] {e}", file=sys.stderr)
        sys.exit(1)
