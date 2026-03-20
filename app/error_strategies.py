"""Centralized error classification for Telegram API errors.

Maps Telethon exception types to recovery strategies so the transfer engine
can handle them consistently without a long if/elif chain.
"""

from enum import StrEnum

from telethon import errors as tg


class Strategy(StrEnum):
    retry = "retry"  # exponential backoff, up to max attempts
    skip = "skip"  # mark message as skipped, continue
    pause = "pause"  # auto-pause job, user must resume
    fail = "fail"  # abort entire job (fatal)


class FileTooLargeError(Exception):
    """Raised when a file exceeds Telegram's upload limit."""


# (exception_type, strategy, human-readable reason)
_ERROR_MAP: list[tuple[type, Strategy, str]] = [
    # ── Fatal: stop the job ──
    (tg.AuthKeyUnregisteredError, Strategy.fail, "Auth key expired — re-login required"),
    (tg.UserDeactivatedBanError, Strategy.fail, "Account deactivated or banned"),
    (tg.UserDeactivatedError, Strategy.fail, "Account deactivated"),
    # ── Skip: cannot transfer this message ──
    (FileTooLargeError, Strategy.skip, "File too large to upload"),
    (tg.MessageIdInvalidError, Strategy.skip, "Message ID invalid or deleted"),
    (tg.MediaCaptionTooLongError, Strategy.skip, "Caption too long"),
    (tg.MessageTooLongError, Strategy.skip, "Message text too long"),
    (tg.FilePartsInvalidError, Strategy.skip, "File too large to upload"),
    (tg.FilePartTooBigError, Strategy.skip, "File part too large"),
    (tg.FilePartSizeInvalidError, Strategy.skip, "Invalid file size for upload"),
    (tg.ChatForwardsRestrictedError, Strategy.skip, "Forwards restricted in this chat"),
    (tg.ChatWriteForbiddenError, Strategy.skip, "Cannot write to destination chat"),
    (tg.MediaEmptyError, Strategy.retry, "Media unavailable"),
    (tg.FileReferenceExpiredError, Strategy.retry, "File reference expired"),
    # ── Pause: rate limit or server issue ──
    (tg.FloodWaitError, Strategy.pause, "Rate limited by Telegram"),
    # ── Retry: transient errors ──
    (ConnectionError, Strategy.retry, "Connection lost"),
    (OSError, Strategy.retry, "Network error"),
    (TimeoutError, Strategy.retry, "Request timeout"),
]


def classify(exc: Exception) -> tuple[Strategy, str]:
    """Return (strategy, reason) for the given exception."""
    for exc_type, strategy, reason in _ERROR_MAP:
        if isinstance(exc, exc_type):
            return strategy, reason
    # Unknown errors: fail rather than retry (non-transient assumption —
    # programming bugs and unexpected errors won't fix themselves on retry)
    return Strategy.fail, "Unexpected error"
