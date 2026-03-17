# Telegram Message Migrator

A personal tool for migrating messages between two Telegram accounts. Log into both accounts, browse chats from the source account, and bulk-forward or copy messages to the destination account.

## Architecture

```
┌──────────────────────────────────────────────────────┐
│            FastAPI + Jinja2/HTMX (port 8000)         │
│                                                       │
│  Browser ◄──── HTML + HTMX ────► FastAPI Routes      │
│            SSE (transfer progress)    │               │
│            REST (auth, chats, control)│               │
│                                       ▼               │
│                              Telethon (MTProto)       │
│                              Account A + Account B    │
│                                       │               │
│                              SQLite (checkpoints)     │
└──────────────────────────────────────────────────────┘
```

- **Single Python process** — no separate frontend server
- **Jinja2 + HTMX** for dynamic UI without JavaScript frameworks
- **Tailwind CSS** (CDN) for styling with dark mode default
- **Telethon** for Telegram MTProto API access
- **SQLite** for transfer checkpoints and job history

## Features

1. **Dual Account Login** — phone → verification code → optional 2FA password
2. **Chat Browser** — list all dialogs from source account, preview messages
3. **Transfer Configuration** — choose mode (Forward/Copy), target, date range filter
4. **Bulk Transfer** — real-time SSE progress, pause/resume, checkpoint-based recovery
5. **Rate Limiting** — conservative delays with jitter to avoid account restrictions

### Transfer Modes

| Mode | Description | Pros | Cons |
|------|-------------|------|------|
| **Forward** (default) | Uses `forward_messages()` | Fast, preserves metadata | Shows "Forwarded from" label |
| **Copy** | Downloads media, re-sends as new message | No source label | Slower, needs temp storage |

## Prerequisites

- **Python** 3.11+
- **Telegram API credentials**: register at [my.telegram.org](https://my.telegram.org) to get `api_id` and `api_hash`

## Setup

1. Clone and enter the project:

   ```bash
   git clone https://github.com/<your-username>/telegram-message-migrator.git
   cd telegram-message-migrator
   ```

2. Copy the environment template and add your credentials:

   ```bash
   cp .env.example .env
   # Edit .env with your api_id and api_hash
   ```

3. Install dependencies and run:

   ```bash
   pip install -r requirements.txt
   uvicorn main:app --reload --port 8000
   ```

4. Open [http://localhost:8000](http://localhost:8000) in your browser.

## Project Structure

```
telegram-message-migrator/
├── main.py                  # FastAPI entrypoint
├── config.py                # Environment config (Pydantic BaseSettings)
├── models.py                # Pydantic schemas
├── database.py              # SQLite (aiosqlite)
├── telegram_client.py       # Dual-account Telethon session manager
├── transfer_engine.py       # Transfer engine + rate limiter
├── routes/
│   ├── auth.py              # Login/logout (REST)
│   ├── chats.py             # List dialogs, fetch messages (REST)
│   └── transfer.py          # Transfer jobs (REST + SSE progress)
├── templates/               # Jinja2 + HTMX templates
│   ├── base.html
│   ├── index.html
│   └── partials/
├── static/
├── requirements.txt
├── .env.example
├── CLAUDE.md
└── README.md
```

## License

MIT
