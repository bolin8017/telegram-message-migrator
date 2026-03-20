from app.models import TransferJobCreate, TransferMode, TransferProgress, TransferStatus


def test_transfer_job_defaults():
    job = TransferJobCreate(source_chat_id=123)
    assert job.mode == TransferMode.forward
    assert job.target_type.value == "saved_messages"
    assert job.target_chat_id is None
    assert job.date_from is None


def test_transfer_progress_defaults():
    p = TransferProgress()
    assert p.total_messages == 0
    assert p.percent == 0.0
    assert p.is_rate_limited is False


def test_transfer_status_values():
    assert TransferStatus.pending.value == "pending"
    assert TransferStatus.running.value == "running"
    assert TransferStatus.completed.value == "completed"


def test_transfer_progress_mode_field():
    from app.models import TransferProgress

    p = TransferProgress()
    assert p.mode is None
    p2 = TransferProgress(mode="relay_forward")
    assert p2.mode == "relay_forward"
