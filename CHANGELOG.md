# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `SECURITY.md` describing the vulnerability disclosure process via GitHub Private Vulnerability Reporting.
- `CHANGELOG.md` and `.editorconfig`.
- `scripts/gcp-bootstrap.md` documenting first-time GCP + Cloudflare provisioning.
- Caddy now trusts Cloudflare's published edge IP ranges and reads the real client IP from `CF-Connecting-IP`.
- Dependabot config for pip, npm, github-actions, and docker ecosystems (weekly, with minor/patch grouped).
- CI security scans: Bandit (Python SAST), pip-audit (Python deps), audit-ci (npm production deps), Trivy (container image). Severity gates set to high/critical block, lower tolerated.
- CI now enforces Conventional Commits 1.0.0 for PR titles via amannn/action-semantic-pull-request.
- `TLS_MODE` env var so the same Caddyfile supports auto Let's Encrypt (self-host) and `tls internal` (behind Cloudflare proxy).
- `OPERATIONS.md` runbook covering deploy / restart / backup / restore / incident playbooks.
- `scripts/backup.sh` for crash-consistent SQLite backups (via `VACUUM INTO`) plus sessions tarball; retention configurable via `RETENTION_DAYS`.
- `LOG_FORMAT` env var for optional JSON-structured logs (`text` remains the default).

### Changed

- CORS allowed origins are now configured via the `CORS_ORIGINS` environment variable instead of being hard-coded.
- `docker-compose.yml` image name corrected from the `ghcr.io/user/...` placeholder to `ghcr.io/bolin8017/telegram-message-migrator`, with `pull_policy: always` so `docker compose up -d` fetches the latest CI image.
- `scripts/deploy.sh` now runs `docker compose pull` before `up -d`.
- `scripts/server-setup.sh` rewritten to target GCP e2-micro Ubuntu 22.04 x86_64.
- README, CLAUDE.md, CONTRIBUTING.md, and `.env.example` updated to reference the hosted instance at <https://tgmigrate.com>.
- CI's docker job now publishes the `:latest` tag on default-branch pushes; sha tag gets a `sha-` prefix for clarity.
- `npm install` in CI's test-frontend job switched to `npm ci` (lockfile-strict).
- `docker-compose.prod.yml`'s caddy service now reads `.env` so `DOMAIN` and `TLS_MODE` flow through.
- Bumped `cryptography` (>=46.0.7), `python-multipart` (>=0.0.27), `pytest` (>=9.0.3) to address known CVEs.

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
