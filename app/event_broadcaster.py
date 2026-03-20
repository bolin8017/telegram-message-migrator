"""Shared pub-sub broadcaster for SSE event streaming."""

import asyncio


class EventBroadcaster:
    """Base class providing subscribe/unsubscribe/broadcast for async Queue-based SSE."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def _broadcast_sync(self, event_type: str, data: dict) -> None:
        """Non-async broadcast (safe from sync contexts and Telethon callbacks)."""
        msg = {"type": event_type, "data": data}
        dead: list[asyncio.Queue] = []
        for q in self._subscribers:
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                # Backpressure: drop slow subscribers rather than block or lose events
                dead.append(q)
        for q in dead:
            self._subscribers.remove(q)

    async def _broadcast(self, event_type: str, data: dict) -> None:
        """Async wrapper around _broadcast_sync.

        Allows callers in async contexts to await uniformly, and simplifies
        future migration if broadcasting needs async I/O.
        """
        self._broadcast_sync(event_type, data)
