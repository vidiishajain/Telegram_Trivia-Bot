"""File storage on Cloudflare R2 (S3-compatible), async via aioboto3.

R2 speaks the S3 API, so this same code works against any S3-compatible store.
Configure it with the R2_* variables in your `.env`.
R2 S3 docs:   https://developers.cloudflare.com/r2/api/s3/api/
aioboto3 docs: https://aioboto3.readthedocs.io/

Two layers of namespacing keep a shared bucket tidy:
  1. R2_PREFIX (set in .env, usually by your instructor) scopes you into your own
     slice of a shared bucket. It's applied automatically — you never type it.
  2. Within your slice, prefix keys with your project name (a convention you
     follow), e.g. "todo_bot/cat.png". (See CLAUDE.md.)

So a relative key "todo_bot/cat.png" with R2_PREFIX="student07" is stored on the
wire as "student07/todo_bot/cat.png" — but every function here speaks the relative
key, so you don't think about R2_PREFIX at all.

Example:

    from agent.services import storage

    key = await storage.store_file("cat.png", prefix="todo_bot")  # -> "todo_bot/4f3c...png"
    url = await storage.presigned_url(key)
"""

import mimetypes
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aioboto3

from agent.config import get_settings


def _require_r2() -> tuple[str, str, str, str]:
    """Return (account_id, access_key_id, secret, bucket) or raise a clear error."""
    s = get_settings()
    if not (s.r2_account_id and s.r2_access_key_id and s.r2_secret_access_key and s.r2_bucket):
        raise RuntimeError(
            "R2 is not configured. Set R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, "
            "R2_SECRET_ACCESS_KEY and R2_BUCKET in your .env."
        )
    return s.r2_account_id, s.r2_access_key_id, s.r2_secret_access_key, s.r2_bucket


def _scope(key: str) -> str:
    """Add your R2_PREFIX so you stay inside your slice of a shared bucket."""
    prefix = get_settings().r2_prefix.strip("/")
    return f"{prefix}/{key}" if prefix else key


def _unscope(key: str) -> str:
    """Remove your R2_PREFIX so callers always see relative keys."""
    prefix = get_settings().r2_prefix.strip("/")
    head = f"{prefix}/"
    return key[len(head) :] if prefix and key.startswith(head) else key


@asynccontextmanager
async def _bucket() -> AsyncIterator[tuple[Any, str]]:
    """Open an async S3 client pointed at R2. Yields (client, bucket_name)."""
    account_id, access_key_id, secret, bucket = _require_r2()
    session = aioboto3.Session()
    # aioboto3's client context manager isn't fully typed, so we annotate it as Any.
    client_ctx: Any = session.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret,
        region_name="auto",
    )
    async with client_ctx as client:
        yield client, bucket


def new_key(suffix: str = "", *, prefix: str = "") -> str:
    """Build a random, unguessable object key (UUID), keeping a suffix like '.png'.

    Using a UUID means object URLs can't be guessed or enumerated — a simple,
    effective layer of privacy for media you serve over public/presigned URLs.
    """
    name = f"{uuid.uuid4().hex}{suffix}"
    return f"{prefix.rstrip('/')}/{name}" if prefix else name


async def store_file(local_path: str | Path, *, prefix: str = "") -> str:
    """Upload a file under a random UUID key (the recommended way to save files).

    Keeps the original extension, sets the right content-type so browsers render
    it, and returns the full key (e.g. "todo_bot/4f3c...png"). Pair it with
    `presigned_url()` to get a shareable link.
    """
    local_path = Path(local_path)
    key = new_key(local_path.suffix, prefix=prefix)
    await upload_file(local_path, key)
    return key


async def store_bytes(
    data: bytes, *, suffix: str = "", prefix: str = "", content_type: str | None = None
) -> str:
    """Upload in-memory bytes under a random UUID key; returns the key.

    Handy when you already have the data (e.g. you just downloaded a generated
    image) and don't want to write a temp file first.
    """
    key = new_key(suffix, prefix=prefix)
    async with _bucket() as (client, bucket):
        await client.put_object(
            Bucket=bucket,
            Key=_scope(key),
            Body=data,
            ContentType=content_type or "application/octet-stream",
        )
    return key


async def upload_file(local_path: str | Path, key: str) -> None:
    """Upload a local file to the bucket under an exact `key` you choose.

    Prefer `store_file()` unless you specifically need a fixed, known key.
    """
    content_type, _ = mimetypes.guess_type(str(local_path))
    extra: dict[str, Any] | None = {"ContentType": content_type} if content_type else None
    async with _bucket() as (client, bucket):
        await client.upload_file(str(local_path), bucket, _scope(key), ExtraArgs=extra)


async def download_file(key: str, local_path: str | Path) -> None:
    """Download object `key` to a local file."""
    async with _bucket() as (client, bucket):
        await client.download_file(bucket, _scope(key), str(local_path))


async def list_keys(prefix: str = "") -> list[str]:
    """List object keys (relative to your prefix), optionally filtered by `prefix`."""
    async with _bucket() as (client, bucket):
        resp = await client.list_objects_v2(Bucket=bucket, Prefix=_scope(prefix))
        return [_unscope(obj["Key"]) for obj in resp.get("Contents", [])]


async def delete_key(key: str) -> None:
    """Delete object `key` from the bucket."""
    async with _bucket() as (client, bucket):
        await client.delete_object(Bucket=bucket, Key=_scope(key))


def public_url(key: str) -> str:
    """Return a stable, non-expiring public URL for `key` via your custom domain.

    Requires R2_PUBLIC_BASE_URL (e.g. https://files.example.com) and a bucket with
    public access enabled. Unlike presigned_url(), these links never expire — so
    this is what you persist in a database and render later.
    """
    base = get_settings().r2_public_base_url
    if not base:
        raise RuntimeError(
            "R2_PUBLIC_BASE_URL is not set. Add your bucket's public/custom domain "
            "to .env (e.g. https://files.example.com) to build public links."
        )
    return f"{base.rstrip('/')}/{_scope(key)}"


async def presigned_url(key: str, expires_in: int = 3600) -> str:
    """Create a *temporary* shareable URL for `key` (default: 1 hour).

    Use this when the bucket has no public domain. For links you store and show
    later, prefer public_url() — presigned links expire.
    """
    async with _bucket() as (client, bucket):
        return await client.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": _scope(key)}, ExpiresIn=expires_in
        )
