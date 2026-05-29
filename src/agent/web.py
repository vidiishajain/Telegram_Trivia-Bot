"""A tiny web interface for your agent (optional).

Run it with auto-reload:

    uv run fastapi dev src/agent/web.py

Then open http://127.0.0.1:8000/docs to try it in the browser, or POST to /ask.

This mirrors `main.py` (the command-line entrypoint): same agent, a different
"UX". It's a starting point — add your own routes, or swap in your own agent.
FastAPI docs: https://fastapi.tiangolo.com/
"""

from fastapi import FastAPI
from pydantic import BaseModel

from agent.agents.example import Answer, ask
from agent.logging_setup import setup_logging

setup_logging()
app = FastAPI(title="Agent")


class Question(BaseModel):
    question: str


@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok", "hint": "POST a question to /ask, or open /docs"}


@app.post("/ask")
async def ask_endpoint(payload: Question) -> Answer:
    """Ask the example agent a question and get back a typed answer."""
    return await ask(payload.question)
