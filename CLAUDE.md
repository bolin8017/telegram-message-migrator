# Telegram Message Migrator

Personal tool for migrating messages between two Telegram accounts. Pure Python: FastAPI + Telethon + Jinja2/HTMX.

## Architecture

- **Backend + UI**: FastAPI, Telethon (MTProto), Jinja2 templates, HTMX, Tailwind CSS — single process on port 8000
- **Database**: SQLite (aiosqlite) for checkpoints and transfer job history
- **Communication**: REST for CRUD, SSE for real-time transfer progress

## Commands

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# Open http://localhost:8000
```

## Project Structure

```
telegram-message-migrator/
├── main.py                  # FastAPI entrypoint + lifespan
├── config.py                # Pydantic BaseSettings (.env)
├── models.py                # Pydantic request/response schemas
├── database.py              # SQLite via aiosqlite (transfers + messages tables)
├── telegram_client.py       # Dual-account Telethon SessionManager
├── transfer_engine.py       # Transfer state machine + Forward/Copy strategies
├── rate_limiter.py          # Token bucket + FloodWait exponential backoff
├── routes/
│   ├── auth.py              # Login/logout (REST, multi-step)
│   ├── chats.py             # List dialogs, fetch messages (REST)
│   └── transfer.py          # Transfer job management (REST + SSE progress)
├── templates/
│   ├── base.html            # Shared layout (Tailwind CDN + HTMX CDN)
│   ├── index.html            # Main wizard page
│   └── partials/            # HTMX swap fragments
├── static/                  # Minimal custom assets
├── requirements.txt
├── .env
└── .gitignore
```

## Coding Standards

- Use Pydantic models for all request/response schemas (`models.py`)
- Telethon session management through `telegram_client.py` (singleton SessionManager)
- Route modules in `routes/` — one file per domain (auth, chats, transfer)
- Templates in `templates/` — use HTMX `hx-*` attributes for dynamic updates, avoid raw JavaScript
- Single uvicorn worker only (Telethon `.session` files are not thread-safe)

## Key Constraints

- Telegram API credentials (`api_id`, `api_hash`) come from `.env` — never commit
- Telethon `.session` files store auth state — must be in `.gitignore`
- Respect Telegram flood limits — conservative rate limiting with jitter and exponential backoff
- Two concurrent Telethon sessions (Account A + Account B) managed independently via SessionManager
- Use `iter_messages(reverse=True)` for message traversal (auto-pagination, memory efficient)
- Media in Copy mode: download to temp files, not memory (supports up to 4GB)

## Rate Limiting Strategy

- Forward: 3s base delay + 40% jitter per message
- Copy text: 3.5s + 40% jitter
- Copy file: 5s + 30% jitter
- Batch cooldown: 15s pause every 20 messages
- Long pause: 1-3 min random rest every 100 messages
- Daily cap: 1500 messages/day
- FloodWait: obey wait time, halve rate, auto-pause after 2 occurrences in 30 min
- New accounts (<30 days): all delays x2

## Git Conventions

- Conventional Commits 1.0.0: `feat:`, `fix:`, `chore:`, `docs:`, etc.
- Branch naming: `<type>/<short-description>` (e.g., `feat/chat-browser`)
- Never push to `main` directly
- Squash merge PRs; delete branch after merge
