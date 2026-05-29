"""DEMO #2 — "Agent Idea Generator" (web, the kitchen-sink demo)

Type a problem + domain of life, and the app:
  1. researches the domain with Perplexity Sonar (research tier),
  2. has Claude write it up + invent a diagram prompt (balanced tier, typed output),
  3. generates the diagram with fal (nano-banana-2) and persists it to R2,
  4. saves everything to Neon, and renders it at /agentidea/{id}.

It composes the project's *already-tested* services — this file is just wiring.

Run it (needs OPENROUTER_API_KEY, FAL_KEY, R2_*, DATABASE_URL in .env):

    uv run fastapi dev examples/agent_idea_web/app.py

Two patterns worth studying (see this folder's README.md):
  - MIGRATIONS: forward-only SQL in migrations/, applied on startup.
  - ASYNC JOB + STATUS POLL: the slow pipeline runs in the background; the page
    polls a fragment endpoint with HTMX and shows live progress until it's done.
"""

import json
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from loguru import logger
from pydantic import BaseModel
from pydantic_ai import Agent

from agent.config import get_settings
from agent.logging_setup import setup_logging
from agent.services import db, media
from agent.services.llm import Source, build_model, research

HERE = Path(__file__).parent
templates = Jinja2Templates(directory=str(HERE / "templates"))

AUTH_COOKIE = "agentidea_auth"  # holds the app password once you've logged in


# --- data shapes ------------------------------------------------------------


class AgentIdea(BaseModel):
    """One row of the agent_ideas table, as a typed object (our 'row -> Pydantic')."""

    id: str
    domain: str
    status: str  # pending | done | error
    stage: str  # queued | researching | writing | drawing | done
    title: str | None = None
    research: str | None = None
    writeup: str | None = None
    where_to_start: str | None = None
    image_prompt: str | None = None
    image_url: str | None = None
    sources: list[Source] = []
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class IdeaWriteup(BaseModel):
    """The structured output we ask Claude for."""

    title: str
    writeup: str  # a short, encouraging write-up (markdown ok)
    where_to_start: str  # one concrete first step
    image_prompt: str  # a prompt for a simple, clean labeled diagram of the idea


# --- database helpers (raw SQL, mapped to Pydantic) -------------------------


async def create_idea(domain: str) -> str:
    idea_id = uuid4().hex  # unguessable id, used directly in the URL
    await db.execute("INSERT INTO agent_ideas (id, domain) VALUES ($1, $2)", idea_id, domain)
    return idea_id


async def get_idea(idea_id: str) -> AgentIdea | None:
    row = await db.fetchrow("SELECT * FROM agent_ideas WHERE id = $1", idea_id)
    if row is None:
        return None
    data = dict(row)
    # asyncpg hands back jsonb columns as a JSON string; turn it into objects.
    if isinstance(data.get("sources"), str):
        data["sources"] = json.loads(data["sources"])
    return AgentIdea(**data)


async def update_idea(idea_id: str, **fields: Any) -> None:
    """Update the given columns (column names come from our code, never user input)."""
    columns = list(fields)
    assignments = ", ".join(f"{col} = ${i + 2}" for i, col in enumerate(columns))
    await db.execute(
        f"UPDATE agent_ideas SET {assignments}, updated_at = now() WHERE id = $1",
        idea_id,
        *(fields[col] for col in columns),
    )


# --- the pipeline (runs in the background; composes our services) -----------


async def write_idea(domain: str, research_text: str) -> IdeaWriteup:
    agent = Agent(
        build_model("balanced"),  # Claude Sonnet, with a typed output
        output_type=IdeaWriteup,
        system_prompt=(
            "You help a beginner spot ONE concrete, buildable AI-agent opportunity in a domain. "
            "Be warm, vivid, and concrete. Write `writeup` as plain prose (a paragraph or two, "
            "no markdown). `image_prompt` must describe a SIMPLE, clean labeled diagram (boxes "
            "and arrows) of how the agent works — a schematic, not a photo."
        ),
    )
    result = await agent.run(
        f"Domain: {domain}\n\nResearch notes:\n{research_text}\n\nWrite it up."
    )
    return result.output


async def run_pipeline(idea_id: str, domain: str) -> None:
    """The slow work. Updates `stage` as it goes so the page can show progress."""
    try:
        await update_idea(idea_id, stage="researching")
        found = await research(  # Perplexity Sonar: live web answer + source links
            f"Research this domain of human life: '{domain}'. What are the real pains, unmet "
            f"needs, and tools people use today? Be concrete and current, about 200 words."
        )

        await update_idea(
            idea_id,
            stage="writing",
            research=found.text,
            sources=json.dumps([s.model_dump() for s in found.sources]),
        )
        idea = await write_idea(domain, found.text)

        await update_idea(
            idea_id,
            stage="drawing",
            title=idea.title,
            writeup=idea.writeup,
            where_to_start=idea.where_to_start,
            image_prompt=idea.image_prompt,
        )
        result = await media.text_to_image(idea.image_prompt, persist=True, prefix="agentidea")
        image_url = result.files[0].url if result.files else None

        await update_idea(idea_id, status="done", stage="done", image_url=image_url)
        logger.info("agent-idea {} finished", idea_id)
    except Exception as exc:  # noqa: BLE001 — record the failure for the user to see
        logger.exception("agent-idea {} failed", idea_id)
        await update_idea(idea_id, status="error", stage="done", error=str(exc))


# --- web app ----------------------------------------------------------------


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    applied = await db.apply_migrations(HERE / "migrations")
    if applied:
        logger.info("applied migrations: {}", applied)
    yield
    await db.close_pool()


app = FastAPI(title="Agent Idea Generator", lifespan=lifespan)


@app.middleware("http")
async def password_gate(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """If APP_PASSWORD is set, require login before any page. No password set = open
    (fine for local dev). We use an httponly cookie so it's sent automatically with
    every request and poll, and isn't readable by JavaScript."""
    password = get_settings().app_password
    if password and request.url.path != "/login":
        cookie = request.cookies.get(AUTH_COOKIE, "")
        if not secrets.compare_digest(cookie, password):
            return RedirectResponse("/login", status_code=303)
    return await call_next(request)


@app.get("/login")
async def login_form(request: Request) -> Response:
    if not get_settings().app_password:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": False})


@app.post("/login")
async def login(request: Request, password: Annotated[str, Form()]) -> Response:
    expected = get_settings().app_password or ""
    if expected and secrets.compare_digest(password, expected):
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            AUTH_COOKIE, password, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 7
        )
        return response
    return templates.TemplateResponse(request, "login.html", {"error": True}, status_code=401)


@app.get("/")
async def index(request: Request) -> Response:
    return templates.TemplateResponse(request, "index.html", {})


@app.post("/agentidea")
async def submit(
    request: Request,
    background_tasks: BackgroundTasks,
    domain: Annotated[str, Form()],
) -> Response:
    idea_id = await create_idea(domain)
    background_tasks.add_task(run_pipeline, idea_id, domain)  # runs after the response
    return RedirectResponse(url=f"/agentidea/{idea_id}", status_code=303)


@app.get("/agentidea/{idea_id}")
async def page(request: Request, idea_id: str) -> Response:
    idea = await get_idea(idea_id)
    if idea is None:
        return HTMLResponse("Not found", status_code=404)
    return templates.TemplateResponse(request, "page.html", {"idea": idea})


@app.get("/agentidea/{idea_id}/fragment")
async def fragment(request: Request, idea_id: str) -> Response:
    """HTMX polls this. While pending it returns a self-polling partial; when done
    (or errored) it returns the final content without the poll trigger, so it stops."""
    idea = await get_idea(idea_id)
    if idea is None:
        return HTMLResponse("Not found", status_code=404)
    return templates.TemplateResponse(request, "_live.html", {"idea": idea})
