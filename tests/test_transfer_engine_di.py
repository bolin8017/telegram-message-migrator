import asyncio
from unittest.mock import MagicMock

from app.transfer_engine import TransferEngine


def test_engine_accepts_session_manager():
    mock_sm = MagicMock()
    semaphore = asyncio.Semaphore(10)
    engine = TransferEngine(session_manager=mock_sm, semaphore=semaphore)
    assert engine._session_manager is mock_sm
    assert engine._semaphore is semaphore


def test_engine_max_messages_default():
    engine = TransferEngine(session_manager=MagicMock(), semaphore=asyncio.Semaphore(10))
    assert engine._max_messages == 50000


def test_engine_persist_checkpoints_default_true():
    engine = TransferEngine(session_manager=MagicMock())
    assert engine._persist_checkpoints is True


def test_engine_persist_checkpoints_false():
    engine = TransferEngine(session_manager=MagicMock(), persist_checkpoints=False)
    assert engine._persist_checkpoints is False


def test_engine_source_account_b_reverses_clients():
    """When source_account='account_b', engine should read from B and write to A."""
    from app.models import TransferJobCreate

    cfg = TransferJobCreate(source_account="account_b", source_chat_id=123)
    assert cfg.source_account == "account_b"

    from app.telegram_client import opposite_account

    assert opposite_account("account_b") == "account_a"
    assert opposite_account("account_a") == "account_b"


def test_engine_no_module_singleton():
    import app.transfer_engine as mod

    assert not hasattr(mod, "engine"), "Module-level singleton should be removed"
