"""Smoke test: does the example wire up correctly?

This test deliberately makes **no network calls** — it does not call the model
(that would cost money and need a real API key). It only checks that everything
imports and constructs, which catches the most common "I broke the setup" bugs.

Run all tests with:

    uv run pytest
"""

import os

# Provide a fake key so `get_settings()` is happy. We never actually call the API.
os.environ.setdefault("OPENROUTER_API_KEY", "test-key-not-real")


def test_example_agent_constructs() -> None:
    from pydantic_ai import Agent

    from agent.agents.example import Answer, example_agent

    # The agent object built without error.
    assert isinstance(example_agent, Agent)

    # The typed output model validates as we expect.
    answer = Answer(answer="hello", confidence=0.5)
    assert 0.0 <= answer.confidence <= 1.0
