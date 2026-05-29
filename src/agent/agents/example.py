"""A minimal example agent.

It exists to (1) prove your setup works end to end, and (2) show the shape of a
pydantic-ai agent: a model, a system prompt, and a *typed* output. Once you
understand it, copy it into your own agent and delete this file.

pydantic-ai docs: https://ai.pydantic.dev/agents/
"""

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from agent.services.llm import build_model


class Answer(BaseModel):
    """The structured answer we ask the model to return.

    Because we declare the shape with Pydantic, pydantic-ai forces the model to
    return exactly this — already validated. No fragile string parsing.
    """

    answer: str = Field(description="A short, direct answer to the question.")
    confidence: float = Field(ge=0.0, le=1.0, description="How sure you are, from 0 to 1.")


# An agent = a model + a system prompt + (optionally) a typed output.
example_agent = Agent(
    build_model(),
    output_type=Answer,
    system_prompt=(
        "You are a concise assistant. Answer in a single sentence. "
        "Set `confidence` honestly between 0 and 1."
    ),
)


async def ask(question: str) -> Answer:
    """Ask the agent a question and get back a typed `Answer`."""
    result = await example_agent.run(question)
    return result.output
