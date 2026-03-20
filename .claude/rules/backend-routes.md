---
paths:
  - "app/routes/**/*.py"
---

# Backend Route Conventions

- Every endpoint accessing Telegram must call `await sm.is_authorized(account)` before using the client
- Use `_get_engine()` / `_get_live_forwarder()` helpers — they raise HTTPException when unavailable
- Never return success if a critical side-effect failed — include `"warning"` field in response
- Catch specific Telethon exceptions, not bare `except Exception` — use `error_strategies.classify()` for user-facing messages
- Never expose raw `str(e)` to clients — internal details (IPs, paths, class names) leak through exception strings
- Rate limit auth endpoints with `@limiter.limit()` from slowapi
- Cookie settings: `httponly=True`, `samesite="strict"`, `secure` based on deployment config
