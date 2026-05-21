# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Telegram Message Migrator, please report it via [GitHub Private Vulnerability Reporting](https://github.com/bolin8017/telegram-message-migrator/security/advisories/new). Please do not file public issues for security-relevant problems.

We'll acknowledge receipt within 7 days and aim to publish a fix within 30 days.

## Scope

In scope:

- The hosted instance at <https://tgmigrate.com>
- The application code in this repository (FastAPI backend, React frontend)
- The Docker image published at `ghcr.io/bolin8017/telegram-message-migrator`

Out of scope:

- Vulnerabilities in upstream dependencies (Telethon, FastAPI, etc.) — please report directly to those projects
- Social engineering, physical attacks, denial-of-service against the hosted instance
- Issues that require an attacker to already have access to a user's Telegram account
- Vulnerabilities affecting only forks or modified deployments
