"""Entry point — wires an agent to a simple console "UX".

Run it:

    uv run agent

Keep `main.py` thin: it sets up logging, then calls into an agent. As your
project grows, this is where you'd start a Telegram bot, a CLI, a web server, etc.
"""

import asyncio

from loguru import logger

from agent.agents.example import ask
from agent.logging_setup import setup_logging


async def _run() -> None:
    question = "In one sentence: what is an AI agent?"
    logger.info("Asking the model: {!r}", question)
    answer = await ask(question)
    logger.info("Model answered (confidence={:.0%})", answer.confidence)
    print(f"Q: {question}")
    print(f"A: {answer.answer}")
    print(f"   (confidence: {answer.confidence:.0%})")


def main() -> None:
    """Entry point for `uv run agent`."""
    setup_logging()
    asyncio.run(_run())


if __name__ == "__main__":
    main()
