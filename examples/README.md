# Examples

Runnable demos that show the starter's pieces working together. **Read them, run them,
then delete them** — they're here to learn from, not to build on. They import the
project's services (`from agent.services import ...`); they don't reinvent anything.

Both need credentials in `.env` (run `uv run agent-doctor` to check).

Each example is a **folder with its own `docs/`** — filled-in `problem.md`, `user_stories.md`,
`failure_modes.md`, `scenarios.md`, `policy.md`, `architecture.md`, `learnings.md`. Those are
**worked examples of the method** (CLAUDE.md): read them to see what a real, filled-in design
doc looks like before you write your own.

## 1. `build_an_agent/` — a terminal app (CLI / TUI)

Asks what kind of agent you'd like to build, then: researches the topic with Perplexity
Sonar, has Claude turn it into a fun, *typed* suggestion, prints it nicely with `rich`,
and saves it as Markdown.

```bash
uv run python examples/build_an_agent/main.py
```

**What to learn from it:** a two-model pipeline (research → write), a Pydantic
`output_type` for structured results, and a clean terminal UI with `rich`. Needs only
`OPENROUTER_API_KEY`. Design docs: `examples/build_an_agent/docs/`.

## 2. `agent_idea_web/` — a small web app (the kitchen sink)

Type a problem + domain of life; it researches → writes it up + invents a diagram prompt
→ generates the diagram with fal (nano-banana-2) and saves it to R2 → stores everything in
Neon → renders it at `/agentidea/{id}` with live progress.

```bash
uv run fastapi dev examples/agent_idea_web/app.py
# then open http://127.0.0.1:8000
```

Needs `OPENROUTER_API_KEY`, `FAL_KEY`, the `R2_*` keys, and `DATABASE_URL`. Front-end is
Jinja2 + HTMX + Tailwind, all via CDN — no build step. Set `APP_PASSWORD` to put it behind
a login (see Pattern C). Design docs: `examples/agent_idea_web/docs/`.

---

This demo is also the reference for **two patterns you'll reuse in real projects.**

### Pattern A — Database migrations (forward-only SQL)

We don't use an ORM. The database layer is raw SQL (`agent.services.db`), and schema
changes are plain `.sql` files applied in order, each exactly once.

- Put numbered files in a `migrations/` folder: `001_init.sql`, `002_add_column.sql`, …
- Write **forward-only** SQL. **Never edit a file that's already been applied** — add a
  new, higher-numbered one (see how `002_add_research_sources.sql` adds a column on top
  of `001`, rather than editing `001`).
- Apply them once on startup:

  ```python
  from agent.services import db
  await db.apply_migrations("examples/agent_idea_web/migrations")
  ```

- `apply_migrations` records applied files in a `_migrations` table, so it's safe to call
  every startup — already-applied files are skipped. It runs each new file in a transaction.

That's the whole migration story: no extra tools, fully visible, and your schema's history
is just the numbered files.

### Pattern B — Async job + status polling (long work without blocking)

The pipeline takes ~30s — too long to make the browser wait on one request. So we split
"start the work" from "show the result":

1. **Submit** (`POST /agentidea`): create a row with `status='pending'`, kick off the
   pipeline as a **background task**, and immediately redirect to the result page.
2. **The work** (`run_pipeline`) updates a `stage` column as it goes
   (`researching → writing → drawing → done`), and finally sets `status='done'`
   (or `'error'` with a message).
3. **The page** polls a fragment endpoint with HTMX every 2 seconds:
   ```html
   <div hx-get="/agentidea/{id}/fragment" hx-trigger="load, every 2s" hx-swap="outerHTML">…</div>
   ```
   While `pending`, the fragment returns *itself* (keeping the poll alive) and shows the
   current stage. Once `done`/`error`, it returns the final content **without** the
   `hx-trigger`, so polling stops on its own.

This is the general shape for any slow agent task (research, generation, batch work): a
**state machine in a row** (`pending → … → done/error`), a **background worker**, and a
**poll that stops itself**. No websockets, no queue, no JS framework.

### Pattern C — Password-gate anything you deploy

A public URL is public. Before you deploy a web demo, put it behind a password so it isn't
open to the whole internet (and so a stranger can't run up your API bill).

- Set `APP_PASSWORD` in `.env`.
- A small middleware checks every request for a valid auth **cookie**; if it's missing, it
  redirects to `/login`. A correct password sets an **httponly** cookie that the browser
  then sends automatically with every request (and every poll).
- No password set → the app is open, which is fine for local development.

Why a cookie and not `localStorage`? In a server-rendered + HTMX app the cookie is sent
automatically with no JavaScript, and being httponly it can't be read by scripts (so an XSS
bug can't steal it). `localStorage` would need JS to attach the value to every request and
is readable by any script on the page.

This is a *gate*, not bank-grade auth — perfect for keeping class demos private.
