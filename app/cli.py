"""CLI entry point: `telegram-migrator` or `python -m app.cli`."""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="telegram-migrator",
        description="Telegram Message Migrator — web UI for migrating messages between accounts.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("uvicorn not installed. Run: pip install telegram-message-migrator", file=sys.stderr)
        sys.exit(1)

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=1,  # Telethon sessions are not thread-safe
    )


if __name__ == "__main__":
    main()
