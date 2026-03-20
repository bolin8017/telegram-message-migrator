---
paths:
  - "tests/**/*.py"
---

# Backend Test Conventions

- Shared fixtures live in `tests/conftest.py` — use `TEST_API_ID`, `TEST_API_HASH`, `TEST_SERVER_SECRET` constants
- `reset_settings_cache` and `clear_user_context_registry` are autouse fixtures from conftest — don't re-define them
- Use `pytest.raises(SpecificException)` — never `pytest.raises(Exception)`
- Follow Arrange-Act-Assert pattern; one assertion focus per test
- Mock Telethon clients (external API), use real SQLite in-memory DB (via `tmp_path`)
- Route tests use `httpx.AsyncClient` with ASGI transport — not mock requests
- asyncio_mode = "auto" in pyproject.toml — no need for `@pytest.mark.asyncio`
