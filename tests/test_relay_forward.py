from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import init_settings
from app.live_forwarder import LiveForwarder
from app.transfer_engine import TransferEngine

from .conftest import TEST_API_HASH, TEST_API_ID


@pytest.fixture(autouse=True)
def _setup_settings(monkeypatch):
    """Set required env vars and initialize settings for relay forward tests."""
    monkeypatch.setenv("TELEGRAM_API_ID", TEST_API_ID)
    monkeypatch.setenv("TELEGRAM_API_HASH", TEST_API_HASH)
    init_settings()


def test_engine_has_relay_state():
    engine = TransferEngine(session_manager=MagicMock(), persist_checkpoints=False)
    assert engine._relay_a is None
    assert engine._relay_b is None
    assert engine._pending_relay_ids == []
    assert engine._source_entity_a is None


def test_get_op_type_relay_forward():
    engine = TransferEngine(session_manager=MagicMock(), persist_checkpoints=False)
    engine._effective_mode = "relay_forward"
    msg = MagicMock(media=None)
    assert engine._get_op_type(msg) == "relay_forward"
    msg_with_media = MagicMock(media=MagicMock())
    assert engine._get_op_type(msg_with_media) == "relay_forward"


def test_get_op_type_forward_and_copy():
    engine = TransferEngine(session_manager=MagicMock(), persist_checkpoints=False)
    engine._effective_mode = "forward"
    assert engine._get_op_type(MagicMock(media=None)) == "forward"
    engine._effective_mode = "copy"
    assert engine._get_op_type(MagicMock(media=MagicMock())) == "copy_file"
    assert engine._get_op_type(MagicMock(media=None)) == "copy_text"


@pytest.mark.asyncio
async def test_transfer_message_relay_forward_branch():
    """relay_forward should forward via relay: source→relay, then relay→dest."""
    mock_sm = MagicMock()
    engine = TransferEngine(session_manager=mock_sm, persist_checkpoints=False)
    engine._effective_mode = "relay_forward"
    engine._relay_a = MagicMock()
    engine._relay_b = MagicMock()
    engine._source_entity_a = MagicMock()
    engine.config = MagicMock(source_chat_id=111)

    source_client = AsyncMock()
    dest_client = AsyncMock()
    msg = MagicMock(id=42)

    relay_msg = MagicMock(id=99)
    source_client.forward_messages = AsyncMock(return_value=[relay_msg])
    dest_client.forward_messages = AsyncMock()

    result = await engine._transfer_message(None, source_client, dest_client, MagicMock(), None, msg, "relay_forward")
    assert result == "done"
    source_client.forward_messages.assert_awaited_once()
    dest_client.forward_messages.assert_awaited_once()
    assert 99 in engine._pending_relay_ids


@pytest.mark.asyncio
async def test_relay_forward_downgrades_on_forwards_restricted():
    """ChatForwardsRestrictedError should downgrade to copy and retry."""
    from telethon import errors as tg_errors

    mock_sm = MagicMock()
    engine = TransferEngine(session_manager=mock_sm, persist_checkpoints=False)
    engine._effective_mode = "relay_forward"
    engine._relay_a = MagicMock()
    engine._relay_b = MagicMock()
    engine._source_entity_a = MagicMock()
    engine.config = MagicMock(source_chat_id=111)
    engine.progress = MagicMock(mode="relay_forward")

    source_client = AsyncMock()
    dest_client = AsyncMock()
    msg = MagicMock(id=42, text="hello", media=None, entities=None)

    source_client.forward_messages = AsyncMock(side_effect=tg_errors.ChatForwardsRestrictedError(request=None))
    dest_client.send_message = AsyncMock()

    await engine._transfer_message(None, source_client, dest_client, MagicMock(), None, msg, "relay_forward")
    assert engine._effective_mode == "copy"
    assert engine.progress.mode == "copy"


def test_live_forwarder_has_relay_state():
    lf = LiveForwarder(session_manager=MagicMock())
    assert lf._relay_a is None
    assert lf._relay_b is None
    assert lf._pending_relay_ids == []
