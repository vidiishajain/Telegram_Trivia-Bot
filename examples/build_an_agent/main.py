"""DEMO #1 — "What agent should I build?" (terminal / TUI)

A small, complete example you can run, read, and then delete. It shows:
  - asking the user a question in the terminal (rich)
  - a two-model pipeline: Perplexity `sonar` researches the topic (live web),
    then Claude (`balanced`) turns it into a fun, crisp, *typed* suggestion
  - saving the result as a Markdown file and displaying it nicely

Run it (needs OPENROUTER_API_KEY in your .env):

    uv run python examples/build_an_agent.py

It imports the project's services — that's the point: examples consume
`agent.services`, they don't reinvent them.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from agent.services.llm import build_model

console = Console()
IDEAS_DIR = Path("ideas")


class AgentIdea(BaseModel):
    """A fun, concrete agent idea a beginner could actually build."""

    title: str = Field(description="A short, catchy name for the agent.")
    one_liner: str = Field(description="A single crisp sentence pitching it.")
    why_it_is_fun: str = Field(description="2-3 sentences on why it's delightful to build.")
    what_it_does: list[str] = Field(description="3-5 bullet points of what it actually does.")
    services_to_use: list[str] = Field(
        description="Which starter services it would use: any of 'llm', 'media', 'storage', 'db'."
    )
    first_step: str = Field(description="The very first concrete step to start building today.")


def to_markdown(idea: AgentIdea) -> str:
    what = "\n".join(f"- {item}" for item in idea.what_it_does)
    services = ", ".join(f"`{s}`" for s in idea.services_to_use)
    return (
        f"# {idea.title}\n\n"
        f"**{idea.one_liner}**\n\n"
        f"{idea.why_it_is_fun}\n\n"
        f"## What it does\n{what}\n\n"
        f"## Services it would use\n{services}\n\n"
        f"## Where to start\n{idea.first_step}\n"
    )


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "idea"


async def dream_up_idea(topic: str) -> AgentIdea:
    """Research the topic with sonar, then design a crisp idea with Claude."""
    with console.status("[bold cyan]Researching with Perplexity Sonar…", spinner="dots"):
        researcher = Agent(build_model("research"))
        research = await researcher.run(
            f"Research the current landscape, fun angles, and gaps for AI agents related to: "
            f"{topic}. Give concrete, current examples. Keep it under 200 words."
        )

    with console.status("[bold green]Designing your idea with Claude…", spinner="dots"):
        designer = Agent(
            build_model("balanced"),
            output_type=AgentIdea,
            system_prompt=(
                "You are a witty, encouraging mentor helping a beginner pick their first AI "
                "agent to build. Be fun and crisp — never corporate. Keep it concrete and doable "
                "with a starter kit that has services for LLMs, media generation, file storage, "
                "and a database."
            ),
        )
        result = await designer.run(
            f"The student is interested in: {topic}\n\n"
            f"Fresh research:\n{research.output}\n\n"
            f"Propose ONE fun, crispy agent idea they could build."
        )
    return result.output


def main() -> None:
    console.print(
        Panel.fit(
            "Let's find a fun first agent for you to build.",
            title="🤖 Agent Idea Generator",
            border_style="cyan",
        )
    )
    topic = Prompt.ask("\n[bold]What kind of agent would you like to build?[/bold]")

    idea = asyncio.run(dream_up_idea(topic))
    markdown = to_markdown(idea)

    console.print()
    console.print(Panel(Markdown(markdown), title=idea.title, border_style="green"))

    IDEAS_DIR.mkdir(exist_ok=True)
    path = IDEAS_DIR / f"{slugify(idea.title)}.md"
    path.write_text(markdown, encoding="utf-8")
    console.print(f"\n[dim]Saved to {path}[/dim]")


if __name__ == "__main__":
    main()
