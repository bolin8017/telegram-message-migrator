from telethon import errors as tg

from app.error_strategies import Strategy, classify

# Telethon RPCError subclasses require a `request` argument
_REQ = None


def test_classify_fatal_errors():
    assert classify(tg.AuthKeyUnregisteredError(request=_REQ))[0] == Strategy.fail
    assert classify(tg.UserDeactivatedBanError(request=_REQ))[0] == Strategy.fail


def test_classify_skip_errors():
    assert classify(tg.MessageIdInvalidError(request=_REQ))[0] == Strategy.skip
    assert classify(tg.ChatForwardsRestrictedError(request=_REQ))[0] == Strategy.skip
    assert classify(tg.ChatWriteForbiddenError(request=_REQ))[0] == Strategy.skip


def test_classify_retry_errors():
    assert classify(ConnectionError())[0] == Strategy.retry
    assert classify(OSError())[0] == Strategy.retry
    assert classify(TimeoutError())[0] == Strategy.retry
    assert classify(tg.MediaEmptyError(request=_REQ))[0] == Strategy.retry


def test_classify_pause_errors():
    exc = tg.FloodWaitError(request=_REQ, capture=30)
    assert classify(exc)[0] == Strategy.pause


def test_classify_unknown_error():
    strategy, reason = classify(ValueError("something weird"))
    assert strategy == Strategy.fail
    assert reason == "Unexpected error"
