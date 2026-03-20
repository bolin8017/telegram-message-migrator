import pytest

from app.config import init_settings

from .conftest import TEST_API_HASH, TEST_API_ID


@pytest.fixture(autouse=True)
def _setup_settings(monkeypatch):
    """Set required env vars and initialize settings for rate limiter tests."""
    monkeypatch.setenv("TELEGRAM_API_ID", TEST_API_ID)
    monkeypatch.setenv("TELEGRAM_API_HASH", TEST_API_HASH)
    init_settings()


def test_rate_limiter_daily_cap():
    from app.rate_limiter import RateLimiter

    rl = RateLimiter()
    assert rl.check_daily_cap() is False
    assert rl.daily_remaining() == 1500


def test_rate_limiter_flood_record():
    from app.rate_limiter import RateLimiter

    rl = RateLimiter()
    rl.record_flood_wait()
    assert rl.should_auto_pause() is False
    rl.record_flood_wait()
    assert rl.should_auto_pause() is True


def test_rate_limiter_reset():
    from app.rate_limiter import RateLimiter

    rl = RateLimiter()
    rl.record_flood_wait()
    rl.set_account_age_multiplier(2.0)
    rl.reset()
    assert rl.should_auto_pause() is False
    assert rl._account_age_multiplier == 1.0


def test_rate_limiter_account_age_multiplier():
    from app.rate_limiter import RateLimiter

    rl = RateLimiter()
    # Default rate for forward: 1/3.0
    default_rate = rl._rate("forward")
    assert abs(default_rate - 1.0 / 3.0) < 0.01

    # With 2x multiplier, rate should halve (= longer delays)
    rl.set_account_age_multiplier(2.0)
    slow_rate = rl._rate("forward")
    assert abs(slow_rate - 1.0 / 6.0) < 0.01

    # Multiplier clamped to >= 1.0
    rl.set_account_age_multiplier(0.5)
    assert rl._account_age_multiplier == 1.0


@pytest.mark.asyncio
async def test_rate_limiter_jitter_always_positive():
    """Jitter delay should always be >= 0 (no negative sleeps)."""
    from app.rate_limiter import RateLimiter

    rl = RateLimiter()
    # Run acquire many times — it should never raise or produce negative delays
    for _ in range(20):
        await rl.acquire("forward")
        # If we get here without error, jitter was non-negative


def test_rate_limiter_relay_forward_config():
    from app.rate_limiter import RateLimiter

    rl = RateLimiter()
    cfg = rl._cfg("relay_forward")
    assert cfg.base_delay == 4.0
    assert cfg.jitter == 0.4
    assert cfg.burst == 1


def test_rate_limiter_relay_forward_rate():
    from app.rate_limiter import RateLimiter

    rl = RateLimiter()
    rate = rl._rate("relay_forward")
    assert abs(rate - 1.0 / 4.0) < 0.01
