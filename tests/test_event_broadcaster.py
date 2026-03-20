"""Tests for app.event_broadcaster — EventBroadcaster pub-sub."""

import asyncio

from app.event_broadcaster import EventBroadcaster


def test_subscribe_returns_queue_and_adds_to_subscribers():
    """subscribe() should return an asyncio.Queue and track it internally."""
    b = EventBroadcaster()
    q = b.subscribe()
    assert isinstance(q, asyncio.Queue)
    assert q in b._subscribers


def test_unsubscribe_removes_from_subscribers():
    """unsubscribe() should remove the queue from internal list."""
    b = EventBroadcaster()
    q = b.subscribe()
    assert q in b._subscribers

    b.unsubscribe(q)
    assert q not in b._subscribers


def test_unsubscribe_nonexistent_is_noop():
    """unsubscribe() with an unknown queue should not raise."""
    b = EventBroadcaster()
    q = asyncio.Queue()
    b.unsubscribe(q)  # should not raise


def test_broadcast_sync_puts_message_in_all_queues():
    """_broadcast_sync should deliver the message to every subscriber."""
    b = EventBroadcaster()
    q1 = b.subscribe()
    q2 = b.subscribe()

    b._broadcast_sync("progress", {"percent": 42})

    expected = {"type": "progress", "data": {"percent": 42}}
    assert q1.get_nowait() == expected
    assert q2.get_nowait() == expected


def test_broadcast_sync_removes_full_queue():
    """A QueueFull subscriber should be automatically removed."""
    b = EventBroadcaster()
    full_q = asyncio.Queue(maxsize=1)
    full_q.put_nowait({"type": "filler", "data": {}})  # fill the queue
    b._subscribers.append(full_q)

    healthy_q = b.subscribe()

    b._broadcast_sync("update", {"value": 1})

    # full_q should have been removed
    assert full_q not in b._subscribers
    # healthy_q should still be subscribed and received the message
    assert healthy_q in b._subscribers
    assert healthy_q.get_nowait() == {"type": "update", "data": {"value": 1}}


async def test_broadcast_async_calls_broadcast_sync():
    """_broadcast (async) should deliver messages same as _broadcast_sync."""
    b = EventBroadcaster()
    q = b.subscribe()

    await b._broadcast("event", {"key": "val"})

    expected = {"type": "event", "data": {"key": "val"}}
    assert q.get_nowait() == expected
