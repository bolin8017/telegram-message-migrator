# Telegram Message Migrator

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/bolin8017/telegram-message-migrator/actions/workflows/ci.yml/badge.svg)](https://github.com/bolin8017/telegram-message-migrator/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![GHCR](https://ghcr-badge.egpl.dev/bolin8017/telegram-message-migrator/latest_tag?label=image&trim=major)](https://github.com/bolin8017/telegram-message-migrator/pkgs/container/telegram-message-migrator)

A self-hosted tool for migrating messages between two Telegram accounts. Log into both accounts, browse chats, and bulk-transfer messages with real-time progress tracking.

> **Hosted instance:** A public instance runs at <https://tgmigrate.com>. There is no registration — log in directly with your Telegram account. Self-host if you prefer running your own copy.

## Features

- **Forward / Copy modes** — forward messages (fast, keeps metadata) or copy as new messages (no "Forwarded from" label)
- **Real-time progress** — SSE-powered live progress bar with pause/resume
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

The hosted instance at <https://tgmigrate.com> runs on:

- **GCP e2-micro** (free tier eligible in `us-west1` / `us-central1` / `us-east1`)
- **Caddy** at the origin for automatic HTTPS via Let's Encrypt
- **Cloudflare** as DNS + edge proxy (orange cloud)

To replicate on your own domain:

1. Provision a VM and DNS. See [`scripts/gcp-bootstrap.md`](scripts/gcp-bootstrap.md) for the full `gcloud` and Cloudflare walk-through.
2. On the VM, set `.env`:
   ```env
   DOMAIN=yourdomain.com
   CORS_ORIGINS=https://yourdomain.com
   SINGLE_USER_MODE=false
   SERVER_SECRET=<32+ chars>
   ```
3. Deploy:
   ```bash
   ./scripts/deploy.sh
   ```

Caddy auto-provisions and renews TLS certificates. The app runs behind the reverse proxy with resource limits (1 CPU, 512 MB RAM). Cloudflare's edge ranges are pre-configured in [`caddy/Caddyfile`](caddy/Caddyfile) so logs see real client IPs.

**TLS modes:**

- **Self-host with public DNS** (no proxy in front): leave `TLS_MODE` unset. Caddy issues a real Let's Encrypt cert via the HTTP-01 challenge.
- **Behind Cloudflare proxy** ("Full" or "Full strict" mode): set `TLS_MODE=tls internal` in `.env` so Caddy uses a self-signed cert at the origin. Cloudflare terminates real TLS at the edge.

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
- **Vulnerability reports**: see [SECURITY.md](SECURITY.md)

## License

MIT
