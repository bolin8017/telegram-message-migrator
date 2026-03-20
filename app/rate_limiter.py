import asyncio
import random
import time
from dataclasses import dataclass, field

from .config import get_settings


@dataclass
class _BucketConfig:
    base_delay: float
    jitter: float
    burst: int


@dataclass
class RateLimiter:
    """Token-bucket rate limiter with adaptive backoff for Telegram API safety."""

    _tokens: dict[str, float] = field(default_factory=dict)
    _last_refill: dict[str, float] = field(default_factory=dict)
    _current_rates: dict[str, float] = field(default_factory=dict)
    _flood_timestamps: list[float] = field(default_factory=list)
    _messages_today: int = 0
    _day_start: float = field(default_factory=time.time)
    _batch_counter: int = 0
    _account_age_multiplier: float = 1.0
    _bucket_configs: dict[str, "_BucketConfig"] | None = None

    def _cfg(self, op: str) -> _BucketConfig:
        if self._bucket_configs is None:
            s = get_settings()
            self._bucket_configs = {
                "forward": _BucketConfig(s.forward_base_delay, s.forward_jitter, s.forward_burst),
                "copy_text": _BucketConfig(s.copy_text_base_delay, s.copy_text_jitter, s.copy_text_burst),
                "copy_file": _BucketConfig(s.copy_file_base_delay, s.copy_file_jitter, s.copy_file_burst),
                "read": _BucketConfig(s.read_base_delay, s.read_jitter, s.read_burst),
                "relay_forward": _BucketConfig(s.relay_forward_base_delay, 0.4, 1),
            }
        return self._bucket_configs.get(op, self._bucket_configs["forward"])

    def _rate(self, op: str) -> float:
        """Current rate (tokens/sec) for the operation type, adjusted for account age."""
        if op not in self._current_rates:
            cfg = self._cfg(op)
            # Slower rate for newer accounts (multiplier > 1 increases delay)
            self._current_rates[op] = 1.0 / (cfg.base_delay * self._account_age_multiplier)
        return self._current_rates[op]

    def set_account_age_multiplier(self, multiplier: float) -> None:
        """Set delay multiplier based on account age. Clears cached rates."""
        self._account_age_multiplier = max(1.0, multiplier)
        self._current_rates.clear()  # force recalculation

    def _refill(self, op: str) -> None:
        cfg = self._cfg(op)
        now = time.time()
        last = self._last_refill.get(op, now)
        elapsed = now - last
        rate = self._rate(op)
        self._tokens[op] = min(
            self._tokens.get(op, float(cfg.burst)) + elapsed * rate,
            float(cfg.burst),
        )
        self._last_refill[op] = now

    async def acquire(self, op: str = "forward") -> None:
        """Wait until a token is available, then consume one."""
        cfg = self._cfg(op)
        while True:
            self._refill(op)
            if self._tokens.get(op, 0) >= 1.0:
                self._tokens[op] -= 1.0
                break
            await asyncio.sleep(0.1)

        # Add jitter for human-like timing variation.
        # random.random() gives uniform [0, 1], so delay is [0, base * jitter].
        # Combined with token bucket (~base_delay), total is ~[base, base*(1+jitter)].
        jitter_delay = cfg.base_delay * cfg.jitter * random.random()
        if jitter_delay > 0:
            await asyncio.sleep(jitter_delay)

    def check_daily_cap(self) -> bool:
        """Returns True if daily cap is reached."""
        now = time.time()
        if now - self._day_start > 86400:
            self._messages_today = 0
            self._day_start = now
        return self._messages_today >= get_settings().daily_message_cap

    def increment_daily(self) -> None:
        self._messages_today += 1

    def daily_remaining(self) -> int:
        return max(0, get_settings().daily_message_cap - self._messages_today)

    async def batch_cooldown(self) -> bool:
        """Check batch counter, sleep if cooldown needed. Returns True if paused."""
        self._batch_counter += 1
        s = get_settings()

        # Long pause every N messages
        if self._batch_counter % s.long_pause_interval == 0:
            pause = random.uniform(s.long_pause_min, s.long_pause_max)
            await asyncio.sleep(pause)
            return True

        # Regular batch cooldown
        if self._batch_counter % s.batch_size == 0:
            jitter = s.batch_cooldown * s.batch_cooldown_jitter
            cooldown = s.batch_cooldown + random.uniform(-jitter, jitter)
            await asyncio.sleep(max(1, cooldown))
            return True

        return False

    def record_flood_wait(self) -> None:
        """Record a FloodWait occurrence and reduce rate."""
        now = time.time()
        self._flood_timestamps.append(now)

        # Halve all rates
        for op in list(self._current_rates.keys()):
            self._current_rates[op] = max(
                self._current_rates[op] * get_settings().flood_rate_reduction,
                get_settings().flood_min_rate,
            )

    def should_auto_pause(self) -> bool:
        """Check if too many FloodWaits occurred in the window."""
        now = time.time()
        window = get_settings().flood_auto_pause_window
        recent = [t for t in self._flood_timestamps if now - t < window]
        self._flood_timestamps = recent
        return len(recent) >= get_settings().flood_auto_pause_count

    def try_recover_rate(self) -> None:
        """Gradually recover rates if no recent FloodWaits."""
        now = time.time()
        if not self._flood_timestamps:
            return
        last_flood = max(self._flood_timestamps)
        if now - last_flood < get_settings().recovery_interval:
            return

        for op in list(self._current_rates.keys()):
            cfg = self._cfg(op)
            max_rate = 1.0 / cfg.base_delay
            self._current_rates[op] = min(
                self._current_rates[op] * get_settings().recovery_factor,
                max_rate,
            )

    def reset(self) -> None:
        """Reset all state for a new transfer job."""
        self._tokens.clear()
        self._last_refill.clear()
        self._current_rates.clear()
        self._flood_timestamps.clear()
        self._batch_counter = 0
        self._account_age_multiplier = 1.0
        self._bucket_configs = None
