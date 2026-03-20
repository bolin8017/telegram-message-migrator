# Contributing

Thanks for your interest in contributing!

## Setup

```bash
git clone https://github.com/<your-username>/telegram-message-migrator.git
cd telegram-message-migrator
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill in your Telegram API credentials
```

Get API credentials at [my.telegram.org](https://my.telegram.org/apps).

## Development

```bash
make dev      # install with dev tools
make run      # start on port 8000
make test     # run tests
make lint     # run linter
make format   # auto-format code
```

## Code Standards

- Python 3.11+, type hints encouraged
- Lint with `ruff`, format with `ruff format`
- Relative imports within `app/` package
- Pydantic models for request/response schemas
- Route modules in `app/routes/` — one file per domain

## Git Conventions

- [Conventional Commits](https://www.conventionalcommits.org/) 1.0.0
- Branch naming: `<type>/<short-description>` (e.g. `feat/live-mode`)
- PR against `main`, squash merge, delete branch after merge
- Never commit `.env`, `.session` files, or secrets

## PR Checklist

- [ ] `make lint` passes
- [ ] `make test` passes
- [ ] CLAUDE.md / README.md updated if needed
- [ ] No secrets committed

## Architecture

See [CLAUDE.md](CLAUDE.md) for project structure, key constraints, and coding standards.
