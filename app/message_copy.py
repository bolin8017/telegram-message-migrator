"""Shared message copy utility for transfer engine and live forwarder."""

import logging
import tempfile

logger = logging.getLogger(__name__)

_CAPTION_LIMIT = 1024  # Telegram media caption max length (longer text sent as separate message)


async def copy_message(dest_client, dest_entity, msg, *, progress_cb=None, upload_limit: int | None = None) -> None:
    """Re-send a message (text and/or media) via dest_client to dest_entity.

    Handles media download, caption splitting, and text-only fallback when
    media download fails.

    Args:
        dest_client: Telethon client for the destination account.
        dest_entity: Destination chat/user entity.
        msg: Source Telethon message object.
        progress_cb: Optional callable(msg_id, phase, total_bytes) returning a
            Telethon progress_callback for download/upload tracking.
        upload_limit: Max file size in bytes. Raises FileTooLargeError if exceeded.
    """
    if msg.media:
        file_size = msg.file.size if msg.file else 0

        if upload_limit and file_size > upload_limit:
            size_gb = round(file_size / (1024**3), 1)
            limit_gb = round(upload_limit / (1024**3), 1)
            from .error_strategies import FileTooLargeError

            raise FileTooLargeError(f"File too large ({size_gb} GB, limit {limit_gb} GB)")

        with tempfile.TemporaryDirectory() as tmpdir:
            download_kwargs: dict = {"file": tmpdir}
            if progress_cb:
                download_kwargs["progress_callback"] = progress_cb(msg.id, "download", file_size)

            logger.debug("Downloading media for msg #%d (%d bytes)", msg.id, file_size)
            path = await msg.download_media(**download_kwargs)

            if path:
                text = msg.text or ""
                upload_kwargs: dict = {}
                if progress_cb:
                    upload_kwargs["progress_callback"] = progress_cb(msg.id, "upload", file_size)

                logger.debug("Uploading file for msg #%d", msg.id)
                if len(text) <= _CAPTION_LIMIT:
                    await dest_client.send_file(
                        dest_entity,
                        path,
                        caption=text,
                        formatting_entities=msg.entities,
                        **upload_kwargs,
                    )
                else:
                    await dest_client.send_file(dest_entity, path, **upload_kwargs)
                    await dest_client.send_message(dest_entity, text, formatting_entities=msg.entities)
            elif msg.text:
                logger.warning("Media download failed for msg #%d, sending text only", msg.id)
                await dest_client.send_message(dest_entity, msg.text, formatting_entities=msg.entities)
            else:
                raise RuntimeError(f"Media download failed for msg #{msg.id} and no text fallback")
    elif msg.text:
        logger.debug("Sending text msg #%d", msg.id)
        await dest_client.send_message(dest_entity, msg.text, formatting_entities=msg.entities)
