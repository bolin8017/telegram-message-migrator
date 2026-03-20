# Telegram Message Migrator

A self-hosted tool for migrating messages between two Telegram accounts. Log into both accounts, browse chats, and bulk-transfer messages with real-time progress tracking.

## Features

- **Forward / Copy modes** — forward messages (fast, keeps metadata) or copy as new messages (no "Forwarded from" label)
- **Real-time progress** — SSE-powered live progress bar with pause/resume and checkpoint recovery
- **Live monitoring** — watch new messages arrive and auto-forward in real time
- **Multi-user support** — optional multi-user mode for shared deployments with per-user encryption
- **Self-hosted** — runs entirely on your own server; no third-party services, no message storage

## Quick Start (Self-Hosted)

```bash
git clone https://github.com/bolin8017/telegram-message-migrator.git
cd telegram-message-migrator
cp .env.example .env
# Edit .env: set TELEGRAM_API_ID and TELEGRAM_API_HASH
# Get credentials at https://my.telegram.org
docker compose up -d
# Open http://localhost:8000
```

## Multi-User Mode

By default, the app runs in single-user mode (no auth required). To enable multi-user mode for shared deployments:

```env
SINGLE_USER_MODE=false
SERVER_SECRET=<generate with: python -c "import secrets; print(secrets.token_urlsafe(32))">
```

Each user provides their own Telegram API credentials and logs in independently. Sessions are encrypted with AES-256-GCM using per-user keys derived via HKDF.

## Production Deployment

Deploy with Caddy as a reverse proxy for automatic HTTPS:

```bash
cp .env.example .env
# Edit .env: set credentials + DOMAIN=yourdomain.com
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Caddy auto-provisions and renews TLS certificates via Let's Encrypt. The app runs behind the reverse proxy with resource limits (1 CPU, 512 MB RAM).

CI/CD is available via GitHub Actions — pushes to `main` build and publish a container image to GHCR.

## Development

### Backend

```bash
make dev-install    # install with dev dependencies (pytest, ruff)
make run            # start FastAPI on port 8000
make test           # run pytest
make lint           # run ruff linter
make format         # format code
```

### Frontend

```bash
make frontend-install  # install npm dependencies
make frontend-dev      # start Vite dev server on port 5173 (proxies /api -> :8000)
make frontend-build    # build to app/static/dist/
make frontend-test     # run Vitest tests
```

Run backend and frontend in separate terminals during development.

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| **Backend** | Python 3.11+, FastAPI, Telethon (MTProto), SQLite (aiosqlite) |
| **Frontend** | React 18, Vite, TypeScript, DaisyUI / Tailwind CSS, Zustand, React Query |
| **Infrastructure** | Docker (multi-stage build), Caddy (auto-HTTPS), GitHub Actions (CI/CD to GHCR) |

## Security

- **Encryption**: Telegram sessions encrypted at rest with AES-256-GCM; per-user keys derived via HKDF
- **No message storage**: messages are streamed through the server, never persisted
- **Open source**: full codebase available for audit

## License

MIT
