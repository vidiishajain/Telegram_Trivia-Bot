"""Integration test: the db (Neon Postgres) service, in isolation.

Two checks against your real database:
  - a plain table round-trip: create → insert → fetch → drop
  - the embeddings → pgvector path: store 1024-dim vectors and confirm a
    similarity search (`<->`) returns the semantically nearest row

Everything uses throwaway `_tests_*` tables and drops them afterward.

    uv run pytest -m integration scripts/tests/test_db_service.py

Skips automatically if DATABASE_URL isn't set in your .env.
"""

import pytest

from agent.config import get_settings


def _db_ready() -> bool:
    try:
        return bool(get_settings().database_url)
    except Exception:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _db_ready(), reason="DATABASE_URL not set in .env"),
]


def _vector_literal(vector: list[float]) -> str:
    """Format a Python list as a pgvector literal, e.g. '[0.1,0.2,...]'."""
    return "[" + ",".join(str(x) for x in vector) + "]"


async def test_table_round_trip() -> None:
    from agent.services import db

    table = "_tests_db_round_trip"
    await db.execute(f"DROP TABLE IF EXISTS {table}")
    await db.execute(f"CREATE TABLE {table} (id serial PRIMARY KEY, body text)")
    try:
        await db.execute(f"INSERT INTO {table} (body) VALUES ($1)", "hello db")
        rows = await db.fetch(f"SELECT body FROM {table}")
        assert [r["body"] for r in rows] == ["hello db"]

        one = await db.fetchrow(f"SELECT body FROM {table} WHERE body = $1", "hello db")
        assert one is not None and one["body"] == "hello db"
    finally:
        await db.execute(f"DROP TABLE IF EXISTS {table}")
        await db.close_pool()


async def test_pgvector_similarity_search() -> None:
    from agent.services import db
    from agent.services.llm import embed_one

    table = "_tests_db_vectors"
    await db.execute("CREATE EXTENSION IF NOT EXISTS vector")
    await db.execute(f"DROP TABLE IF EXISTS {table}")
    await db.execute(
        f"CREATE TABLE {table} (id serial PRIMARY KEY, content text, embedding vector(1024))"
    )
    try:
        documents = ["cats and kittens", "today's stock market", "a recipe for pancakes"]
        for content in documents:
            vector = await embed_one(content)
            await db.execute(
                f"INSERT INTO {table} (content, embedding) VALUES ($1, $2::vector)",
                content,
                _vector_literal(vector),
            )

        query = await embed_one("a small furry pet")
        nearest = await db.fetchrow(
            f"SELECT content FROM {table} ORDER BY embedding <-> $1::vector LIMIT 1",
            _vector_literal(query),
        )
        assert nearest is not None and nearest["content"] == "cats and kittens"
    finally:
        await db.execute(f"DROP TABLE IF EXISTS {table}")
        await db.close_pool()
