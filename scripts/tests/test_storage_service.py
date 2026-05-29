"""Integration test: the storage (R2) service, in isolation.

A full round-trip against your real bucket: store → list → download → fetch the
public URL → delete. It cleans up after itself (everything goes under a "_tests/"
prefix inside your slice).

    uv run pytest -m integration scripts/tests/test_storage_service.py

Skips automatically if R2 isn't configured in your .env.
"""

import httpx
import pytest

from agent.config import get_settings


def _r2_ready() -> bool:
    try:
        s = get_settings()
    except Exception:
        return False
    return bool(s.r2_account_id and s.r2_access_key_id and s.r2_secret_access_key and s.r2_bucket)


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _r2_ready(), reason="R2 not configured in .env"),
]


async def test_store_list_download_delete(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from agent.services import storage

    content = b"hello from the storage isolation test"
    local = tmp_path / "hello.txt"
    local.write_bytes(content)

    key = await storage.store_file(local, prefix="_tests")
    try:
        # store_file gives a UUID key under our prefix
        assert key.startswith("_tests/")
        assert key.endswith(".txt")

        # it shows up in a listing
        assert key in await storage.list_keys("_tests/")

        # it downloads byte-for-byte
        out = tmp_path / "back.txt"
        await storage.download_file(key, out)
        assert out.read_bytes() == content

        # if a public domain is configured, the URL serves the same bytes
        if get_settings().r2_public_base_url:
            url = storage.public_url(key)
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url)
            assert response.status_code == 200
            assert response.content == content
    finally:
        await storage.delete_key(key)

    # gone after delete
    assert key not in await storage.list_keys("_tests/")
