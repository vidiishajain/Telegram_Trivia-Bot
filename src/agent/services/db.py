"""Postgres database (Neon), async via asyncpg.

Neon is serverless Postgres; asyncpg is a fast async driver. We keep a single
connection *pool* and reuse it across the program.

⚠️  You have ONE database, shared across all your projects. To stop projects from
    clobbering each other, prefix your table names with your project, e.g.
    `todo_bot_notes`. (See CLAUDE.md for the shared-resource convention.)

Example:

    from agent.services import db

    await db.execute(
        "CREATE TABLE IF NOT EXISTS todo_bot_notes (id serial primary key, body text)"
    )
    await db.execute("INSERT INTO todo_bot_notes (body) VALUES ($1)", "buy milk")
    rows = await db.fetch("SELECT body FROM todo_bot_notes")
    for row in rows:
        print(row["body"])
"""

from pathlib import Path
from typing import Any

import asyncpg

from agent.config import get_settings

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Return the shared connection pool, creating it on first use."""
    global _pool
    if _pool is None:
        url = get_settings().database_url
        if not url:
            raise RuntimeError("DATABASE_URL is not set. Add your Neon connection string to .env.")
        # statement_cache_size=0 keeps asyncpg working through Neon's connection
        # pooler (pgbouncer), which otherwise breaks asyncpg's prepared statements.
        _pool = await asyncpg.create_pool(dsn=url, statement_cache_size=0)
    return _pool


async def fetch(query: str, *args: Any) -> list[asyncpg.Record]:
    """Run a query and return all rows. Use $1, $2, ... for parameters."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)


async def fetchrow(query: str, *args: Any) -> asyncpg.Record | None:
    """Run a query and return the first row, or None."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, *args)


async def execute(query: str, *args: Any) -> str:
    """Run a statement that returns no rows (INSERT/UPDATE/CREATE/...)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)


async def close_pool() -> None:
    """Close the pool. Call this once on shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def _read_migrations(migrations_dir: str | Path) -> list[tuple[str, str]]:
    """Read (filename, sql) for every *.sql file, in filename order. Plain file I/O."""
    return [
        (path.name, path.read_text(encoding="utf-8"))
        for path in sorted(Path(migrations_dir).glob("*.sql"))
    ]


async def apply_migrations(migrations_dir: str | Path) -> list[str]:
    """Apply every `*.sql` file in `migrations_dir`, in filename order, exactly once.

    This is our migration pattern — no extra tools needed:
      - Name files with a zero-padded number first: 001_init.sql, 002_add_col.sql.
      - Write forward-only SQL (CREATE TABLE, ALTER TABLE, ...). Never edit an
        applied file; add a new, higher-numbered one instead.
      - Each file runs once, inside a transaction, and is recorded in `_migrations`.
      - Safe to call on every startup: already-applied files are skipped.

    Returns the names of the files that were applied this time.
    """
    pool = await get_pool()
    applied: list[str] = []
    async with pool.acquire() as conn:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS _migrations ("
            "  name text PRIMARY KEY,"
            "  applied_at timestamptz NOT NULL DEFAULT now()"
            ")"
        )
        for name, sql in _read_migrations(migrations_dir):
            already = await conn.fetchval("SELECT 1 FROM _migrations WHERE name = $1", name)
            if already:
                continue
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute("INSERT INTO _migrations (name) VALUES ($1)", name)
            applied.append(name)
    return applied
