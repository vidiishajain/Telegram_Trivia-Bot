"""Agents: where your agents live.

An "agent" here is a pydantic-ai `Agent` — a model plus a system prompt, often
with a typed output and some tools. Agents are *composition*: they wire together
the `services/` (llm, media, storage, db) into a behavior.

Start with `example.py`, then add your own (e.g. `researcher.py`, `summarizer.py`).
"""
