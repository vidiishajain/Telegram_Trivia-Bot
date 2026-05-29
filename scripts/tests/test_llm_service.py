"""Tests for the llm service.

Shows both kinds in one file:
  - UNIT tests for the pure tier-resolving logic (offline, always run)
  - INTEGRATION tests for real chat / structured output / embeddings
    (marked `integration`, skipped without OPENROUTER_API_KEY)

    uv run pytest scripts/tests/test_llm_service.py             # unit only
    uv run pytest -m integration scripts/tests/test_llm_service.py  # live
"""

import pytest

from agent.config import get_settings


def _llm_ready() -> bool:
    try:
        return bool(get_settings().openrouter_api_key)
    except Exception:
        return False


requires_llm = pytest.mark.skipif(not _llm_ready(), reason="OPENROUTER_API_KEY not set")


# --- unit: tier resolution (no network) -------------------------------------


def test_resolve_known_tier() -> None:
    from agent.services.llm import TIERS, _resolve

    assert _resolve("balanced") == TIERS["balanced"]


def test_resolve_passes_through_raw_slug() -> None:
    from agent.services.llm import _resolve

    assert _resolve("openai/gpt-5.1") == "openai/gpt-5.1"


def test_resolve_rejects_unknown_name() -> None:
    from agent.services.llm import _resolve

    with pytest.raises(ValueError):
        _resolve("definitely-not-a-tier")


# --- integration: real calls ------------------------------------------------


@pytest.mark.integration
@requires_llm
async def test_chat_non_streaming() -> None:
    from pydantic_ai import Agent

    from agent.services.llm import build_model

    agent = Agent(build_model("fast"))
    result = await agent.run("Reply with exactly the word: pong")
    assert "pong" in result.output.lower()


@pytest.mark.integration
@requires_llm
async def test_chat_streaming() -> None:
    from pydantic_ai import Agent

    from agent.services.llm import build_model

    agent = Agent(build_model("fast"))
    deltas: list[str] = []
    async with agent.run_stream("Count from one to five in words.") as result:
        async for delta in result.stream_text(delta=True):
            deltas.append(delta)

    assert deltas  # we actually received streamed chunks
    assert "".join(deltas).strip()  # that form a non-empty answer


@pytest.mark.integration
@requires_llm
async def test_tool_is_called() -> None:
    from pydantic_ai import Agent

    from agent.services.llm import build_model

    calls: list[tuple[int, int]] = []
    agent = Agent(build_model("fast"))

    @agent.tool_plain
    def add(a: int, b: int) -> int:
        """Add two integers."""
        calls.append((a, b))
        return a + b

    result = await agent.run("Use the add tool to compute 17 + 25, then tell me the number.")
    assert calls  # the tool was genuinely invoked
    assert "42" in result.output


@pytest.mark.integration
@requires_llm
async def test_structured_output() -> None:
    from pydantic import BaseModel
    from pydantic_ai import Agent

    from agent.services.llm import build_model

    class Capital(BaseModel):
        city: str
        country: str

    agent = Agent(build_model("fast"), output_type=Capital)
    result = await agent.run("What is the capital of France?")
    assert result.output.country.lower() == "france"


@pytest.mark.integration
@requires_llm
async def test_embeddings_have_expected_dimension() -> None:
    from agent.services.llm import embed, embed_one

    vector = await embed_one("hello world")
    assert len(vector) == 1024  # baai/bge-m3 dense dimension

    vectors = await embed(["alpha", "beta"])
    assert len(vectors) == 2
    assert all(len(v) == 1024 for v in vectors)
