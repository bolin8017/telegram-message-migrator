---
paths:
  - "app/**/*.py"
---

# Error Handling Policy

- Never use `except Exception: pass` — at minimum `logger.warning(..., exc_info=True)`
- `except Exception: pass` in cleanup/finally is allowed ONLY with `logger.debug` logging
- Move cleanup actions (`.clear()`, resource release) into `finally` blocks, not inside `try`
- Catch specific exception types before generic ones: `except (ValueError, ConnectionError)` not `except Exception`
- When wrapping exceptions, preserve the original: `raise NewError(...) from e`
- `error_strategies.classify()` returns user-safe (strategy, reason) — use `reason` for client-facing messages
- Unknown errors default to `Strategy.fail` (not retry) — programming bugs don't fix themselves
