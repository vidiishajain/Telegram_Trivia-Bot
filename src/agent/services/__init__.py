"""Services: thin, typed, async wrappers around the outside world.

Each module here talks to ONE external thing and nothing else, so you can test
it in isolation:

    llm.py      -> language models, via OpenRouter (pydantic-ai)
    media.py    -> image/video/audio generation, via fal.ai
    storage.py  -> file storage, via Cloudflare R2 (S3-compatible)
    db.py       -> Postgres database, via Neon (asyncpg)

This `__init__.py` deliberately imports nothing, so importing one service never
drags in the others.
"""
