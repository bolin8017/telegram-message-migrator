# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

_(nothing yet)_

## [0.3.0] - 2026-05-21

### Added

- `SECURITY.md` describing the vulnerability disclosure process via GitHub Private Vulnerability Reporting.
- `CHANGELOG.md` and `.editorconfig`.
- `scripts/gcp-bootstrap.md` documenting first-time GCP + Cloudflare provisioning.
- `OPERATIONS.md` runbook covering deploy / restart / backup / restore / incident playbooks.
- `scripts/backup.sh` for crash-consistent SQLite backups (via `VACUUM INTO`) plus sessions tarball; retention configurable via `RETENTION_DAYS`.
- Caddy now trusts Cloudflare's published edge IP ranges and reads the real client IP from `CF-Connecting-IP`.
- `TLS_MODE` env var so the same Caddyfile supports auto Let's Encrypt (self-host) and `tls internal` (behind Cloudflare proxy).
- `LOG_FORMAT` env var for optional JSON-structured logs (`text` remains the default).
- Dependabot config for pip, npm, github-actions, and docker ecosystems (weekly, with minor/patch grouped).
- CI security scans: Bandit (Python SAST), pip-audit (Python deps), audit-ci (npm production deps), Trivy (container image, advisory). Severity gates set to high/critical block, lower tolerated.
- CI now enforces Conventional Commits 1.0.0 for PR titles via amannn/action-semantic-pull-request.
- README badges (license, CI, Python, GHCR image).

### Changed

- CORS allowed origins are now configured via the `CORS_ORIGINS` environment variable instead of being hard-coded.
- `docker-compose.yml` image name corrected from the `ghcr.io/user/...` placeholder to `ghcr.io/bolin8017/telegram-message-migrator`, with `pull_policy: always` so `docker compose up -d` fetches the latest CI image.
- `scripts/deploy.sh` now runs `docker compose pull` before `up -d`.
- `scripts/server-setup.sh` rewritten to target GCP e2-micro Ubuntu 22.04 x86_64.
- README, CLAUDE.md, CONTRIBUTING.md, and `.env.example` updated to reference the hosted instance at <https://tgmigrate.com>.
- CI's docker job now publishes the `:latest` tag on default-branch pushes; sha tag gets a `sha-` prefix for clarity.
- `docker-compose.prod.yml`'s caddy service now reads `.env` so `DOMAIN` and `TLS_MODE` flow through.
- Bumped direct deps for known CVEs and currency: `cryptography` (>=46.0.7), `python-multipart` (>=0.0.27), `pytest` (>=9.0.3), `typescript` 5.9 → 6.0, `react-day-picker` 9 → 10, plus a grouped npm minor/patch update (`@tanstack/react-query`, `@tanstack/react-virtual`, `autoprefixer`, `jsdom`, `postcss`, `vitest`).
- Bumped 5 GitHub Actions: `actions/setup-node` 4→6, `docker/build-push-action` 6→7, `amannn/action-semantic-pull-request` 5→6, `docker/login-action` 3→4, `docker/metadata-action` 5→6.
- `frontend/tsconfig.json` drops deprecated `baseUrl` (TypeScript 6 deprecation).
- Bandit false positives in `app/database.py` and `app/rate_limiter.py` annotated with `# nosec` + rationale so ad-hoc audits stay quiet.

### Removed

- Legacy Jinja2 templates under `app/templates/` and the `jinja2` dependency — the React SPA has been the sole frontend since v0.1.0.
- Oracle Cloud (OCI) provisioning scripts (`scripts/oci-create-instance.sh`, `scripts/oci-grab-setup.sh`).
- Stale `.gitignore` entries for the removed OCI scripts.
- Root-level residues: `routes/`, `__pycache__/`, `data.db*`, `node_modules/`, `.superpowers/`, `.pytest_cache/`, `.ruff_cache/`.
- `frontend/tsconfig.tsbuildinfo` is no longer tracked.

## [0.1.0] - 2026-03-19

### Added

- Initial release: FastAPI + Telethon backend, React SPA frontend.
- Forward and Copy transfer modes with rate limiting.
- Multi-user mode with AES-256-GCM session encryption.
- Live message forwarding via Telethon events.
- Docker Compose + Caddy auto-HTTPS production setup.
