# Telegram Message Migrator

Personal tool for migrating messages between two Telegram accounts. Backend: FastAPI + Telethon. Frontend: React SPA (Vite + DaisyUI/Tailwind).

## Architecture

- **Backend**: FastAPI, Telethon (MTProto) — single process on port 8000
- **Frontend**: React 18 SPA (Vite, TypeScript, DaisyUI/Tailwind, Zustand, React Query) — dev on port 5173, production built to `app/static/dist/`
- **Legacy UI**: Jinja2 templates + HTMX (being replaced by React SPA)
- **Database**: SQLite (aiosqlite) for checkpoints, transfer job history, and multi-user session storage
- **Communication**: REST for CRUD, SSE for real-time transfer progress

## Commands

```bash
make install          # Install dependencies
make run              # Start on port 8000
make dev-install      # Install with dev tools (pytest, ruff)
make dev              # Show full-stack dev instructions
make build            # Build frontend + show next steps
make test             # Run tests
make lint             # Run linter
make format           # Format code

# Frontend:
make frontend-install # Install frontend dependencies
make frontend-dev     # Start Vite dev server on port 5173
make frontend-build   # Build frontend to app/static/dist/
make frontend-test    # Run frontend tests

# Or directly:
pip install -e .
uvicorn app.main:app --reload --port 8000

# Docker:
docker compose up --build

# Production (Caddy auto-HTTPS):
DOMAIN=yourdomain.com docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## Project Structure

```
telegram-message-migrator/
├── app/                         # Python package
│   ├── __init__.py
│   ├── main.py                  # FastAPI entrypoint + lifespan
│   ├── config.py                # Pydantic BaseSettings (.env)
│   ├── models.py                # Pydantic request/response schemas
│   ├── database.py              # SQLite via aiosqlite
│   ├── telegram_client.py       # Dual-account Telethon SessionManager
│   ├── transfer_engine.py       # Transfer state machine + strategies
│   ├── rate_limiter.py          # Token bucket + FloodWait backoff
│   ├── crypto.py                # AES-256-GCM encryption + HKDF key derivation
│   ├── user_context.py          # Per-user state registry (session_token → UserContext)
│   ├── middleware.py             # Session cookie middleware + require_user dependency
│   ├── live_forwarder.py         # Real-time message forwarding via Telethon events
│   ├── routes/
│   │   ├── auth.py              # Login/logout (JSON API, server-side phone_code_hash)
│   │   ├── chats.py             # List dialogs, fetch messages (REST)
│   │   ├── transfer.py          # Transfer jobs (REST + SSE progress)
│   │   ├── live.py              # Live forwarding routes (REST + SSE)
│   │   ├── setup.py             # Credential provisioning (multi-user)
│   │   └── user.py              # User data management (multi-user)
│   ├── templates/               # Jinja2 + HTMX templates
│   └── static/                  # Minimal custom assets
├── frontend/                    # React SPA (Vite + TypeScript)
│   ├── src/                     # React components, stores, hooks
│   ├── tests/                   # Vitest + Testing Library
│   ├── index.html               # SPA entry point
│   ├── package.json
│   ├── vite.config.ts           # Vite config (proxy /api → :8000)
│   ├── tailwind.config.ts       # Tailwind + DaisyUI themes
│   └── tsconfig.json
├── tests/                       # Pytest test suite (backend)
├── pyproject.toml               # Project metadata and dependencies
├── Makefile                     # Common dev tasks
├── Dockerfile                   # Multi-stage build (Node + Python)
├── docker-compose.yml           # Base compose (self-hosted)
├── docker-compose.prod.yml      # Production overlay (Caddy + resource limits)
├── caddy/
│   └── Caddyfile                # Caddy reverse proxy config (auto-HTTPS)
├── .env.example
└── LICENSE
```

## Coding Standards

- Use relative imports within the `app/` package (e.g., `from .config import settings`)
- Use Pydantic models for all request/response schemas (`app/models.py`)
- Telethon session management through `app/telegram_client.py` (injected SessionManager, no module-level singleton)
- Route modules in `app/routes/` — one file per domain (auth, chats, transfer)
- Templates in `app/templates/` — use HTMX `hx-*` attributes for dynamic updates
- Single uvicorn worker only (Telethon `.session` files are not thread-safe)
- Lint with `ruff`, format with `ruff format`

### Frontend

- React 18 with TypeScript strict mode
- State: Zustand for global state, React Query for server state
- Styling: Tailwind CSS + DaisyUI component library
- Routing: React Router v6
- Testing: Vitest + Testing Library
- Path alias: `@/*` maps to `./src/*`
- Vite dev server proxies `/api` and `/health` to FastAPI at `:8000`
- Production build outputs to `app/static/dist/`

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
