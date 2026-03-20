import pytest

from app.user_context import (
    RegistryFullError,
    SessionLimitError,
    UserContext,
    _user_sessions,
    get_all_contexts,
    get_context,
    get_user_session_count,
    register_context,
    remove_context,
)


def test_register_and_get():
    ctx = UserContext(user_id=1, session_token="tok1")
    register_context(ctx)
    assert get_context("tok1") is ctx


def test_remove_context():
    ctx = UserContext(user_id=1, session_token="tok1")
    register_context(ctx)
    remove_context("tok1")
    assert get_context("tok1") is None


def test_remove_nonexistent_is_noop():
    remove_context("nonexistent")  # should not raise


def test_get_user_session_count():
    register_context(UserContext(user_id=99, session_token="a"))
    register_context(UserContext(user_id=99, session_token="b"))
    assert get_user_session_count(99) == 2


def test_max_sessions_per_user():
    for i in range(3):
        register_context(UserContext(user_id=99, session_token=f"t{i}"))
    with pytest.raises(SessionLimitError):
        register_context(UserContext(user_id=99, session_token="t3"))


def test_global_context_limit():
    for i in range(5):
        register_context(UserContext(user_id=i, session_token=f"g{i}"), max_contexts=5)
    with pytest.raises(RegistryFullError):
        register_context(UserContext(user_id=99, session_token="g5"), max_contexts=5)


def test_remove_decrements_user_count():
    register_context(UserContext(user_id=1, session_token="a"))
    register_context(UserContext(user_id=1, session_token="b"))
    remove_context("a")
    assert get_user_session_count(1) == 1


def test_remove_last_session_cleans_user_entry():
    register_context(UserContext(user_id=1, session_token="a"))
    remove_context("a")
    assert 1 not in _user_sessions


def test_get_all_contexts():
    ctx1 = UserContext(user_id=1, session_token="tok1")
    ctx2 = UserContext(user_id=2, session_token="tok2")
    register_context(ctx1)
    register_context(ctx2)
    all_ctx = get_all_contexts()
    assert len(all_ctx) == 2
    assert all_ctx["tok1"] is ctx1
    assert all_ctx["tok2"] is ctx2


def test_get_context_nonexistent_returns_none():
    assert get_context("nonexistent") is None


def test_get_user_session_count_unknown_user():
    assert get_user_session_count(999) == 0
