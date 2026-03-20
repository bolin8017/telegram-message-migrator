"""Tests for app.message_copy — copy_message utility."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.error_strategies import FileTooLargeError
from app.message_copy import copy_message


def _make_msg(*, text=None, media=None, file_size=0, entities=None, msg_id=1):
    """Build a minimal mock Telethon Message."""
    msg = MagicMock()
    msg.id = msg_id
    msg.text = text
    msg.media = media
    msg.entities = entities
    if media:
        msg.file = MagicMock()
        msg.file.size = file_size
    else:
        msg.file = None
    msg.download_media = AsyncMock(return_value="/tmp/fakefile.jpg")
    return msg


async def test_text_only_calls_send_message():
    """Text-only message should call send_message, not send_file."""
    dest = AsyncMock()
    entity = MagicMock()
    msg = _make_msg(text="hello", media=None)

    await copy_message(dest, entity, msg)

    dest.send_message.assert_awaited_once_with(entity, "hello", formatting_entities=msg.entities)
    dest.send_file.assert_not_awaited()


async def test_media_short_caption_calls_send_file_with_caption():
    """Media with short caption (<=1024) should call send_file(caption=...)."""
    dest = AsyncMock()
    entity = MagicMock()
    short_text = "short caption"
    msg = _make_msg(text=short_text, media=True, file_size=1024)

    await copy_message(dest, entity, msg)

    dest.send_file.assert_awaited_once()
    call_kwargs = dest.send_file.call_args
    assert call_kwargs.kwargs["caption"] == short_text
    dest.send_message.assert_not_awaited()


async def test_media_long_caption_calls_send_file_then_send_message():
    """Media with long caption (>1024) should call send_file then send_message."""
    dest = AsyncMock()
    entity = MagicMock()
    long_text = "x" * 1025
    msg = _make_msg(text=long_text, media=True, file_size=1024)

    await copy_message(dest, entity, msg)

    dest.send_file.assert_awaited_once()
    # send_file should NOT have caption kwarg
    call_kwargs = dest.send_file.call_args
    assert "caption" not in call_kwargs.kwargs
    dest.send_message.assert_awaited_once_with(entity, long_text, formatting_entities=msg.entities)


async def test_media_download_fails_but_has_text_sends_text():
    """When media download returns None but msg has text, send text only."""
    dest = AsyncMock()
    entity = MagicMock()
    msg = _make_msg(text="fallback text", media=True, file_size=500)
    msg.download_media = AsyncMock(return_value=None)

    await copy_message(dest, entity, msg)

    dest.send_message.assert_awaited_once_with(entity, "fallback text", formatting_entities=msg.entities)
    dest.send_file.assert_not_awaited()


async def test_media_download_fails_no_text_raises_runtime_error():
    """When media download returns None and no text, raise RuntimeError."""
    dest = AsyncMock()
    entity = MagicMock()
    msg = _make_msg(text=None, media=True, file_size=500)
    msg.download_media = AsyncMock(return_value=None)

    with pytest.raises(RuntimeError, match="Media download failed"):
        await copy_message(dest, entity, msg)


async def test_upload_limit_exceeded_raises_file_too_large():
    """When file_size > upload_limit, raise FileTooLargeError."""
    dest = AsyncMock()
    entity = MagicMock()
    msg = _make_msg(text="caption", media=True, file_size=5 * 1024**3)

    with pytest.raises(FileTooLargeError, match="File too large"):
        await copy_message(dest, entity, msg, upload_limit=2 * 1024**3)

    dest.send_file.assert_not_awaited()
    dest.send_message.assert_not_awaited()


async def test_progress_cb_passed_through():
    """progress_cb should be called for download and upload phases."""
    dest = AsyncMock()
    entity = MagicMock()
    file_size = 2048
    msg = _make_msg(text="cap", media=True, file_size=file_size)

    progress_cb = MagicMock()
    download_progress = MagicMock()
    upload_progress = MagicMock()
    progress_cb.side_effect = lambda msg_id, phase, total: download_progress if phase == "download" else upload_progress

    await copy_message(dest, entity, msg, progress_cb=progress_cb)

    # progress_cb should be called for download and upload
    assert progress_cb.call_count == 2
    progress_cb.assert_any_call(msg.id, "download", file_size)
    progress_cb.assert_any_call(msg.id, "upload", file_size)

    # download_media should receive progress_callback
    dl_kwargs = msg.download_media.call_args.kwargs
    assert dl_kwargs["progress_callback"] is download_progress

    # send_file should receive progress_callback
    sf_kwargs = dest.send_file.call_args.kwargs
    assert sf_kwargs["progress_callback"] is upload_progress
