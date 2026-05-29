"""Unit tests for storage key handling — pure logic, no network or credentials.

Shows the pattern: test the small, pure pieces of a service in isolation.

    uv run pytest
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key-not-real")


def test_new_key_has_prefix_and_suffix() -> None:
    from agent.services.storage import new_key

    key = new_key(".png", prefix="todo_bot")
    assert key.startswith("todo_bot/")
    assert key.endswith(".png")
    # There's a uuid between the prefix and the suffix.
    assert len(key) > len("todo_bot/.png")


def test_scope_and_unscope_round_trip(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("R2_PREFIX", "student07")
    from agent.config import get_settings
    from agent.services import storage

    get_settings.cache_clear()  # re-read settings with the patched env
    try:
        scoped = storage._scope("todo_bot/cat.png")
        assert scoped == "student07/todo_bot/cat.png"
        assert storage._unscope(scoped) == "todo_bot/cat.png"
        # Unscoping a key that lacks the prefix leaves it untouched.
        assert storage._unscope("other/cat.png") == "other/cat.png"
    finally:
        get_settings.cache_clear()  # reset cache for any later tests


def test_public_url_includes_prefix(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("R2_PREFIX", "student07")
    monkeypatch.setenv("R2_PUBLIC_BASE_URL", "https://files.example.com/")
    from agent.config import get_settings
    from agent.services import storage

    get_settings.cache_clear()
    try:
        url = storage.public_url("todo_bot/cat.png")
        assert url == "https://files.example.com/student07/todo_bot/cat.png"
    finally:
        get_settings.cache_clear()
