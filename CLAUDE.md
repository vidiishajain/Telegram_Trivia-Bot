# CLAUDE.md

Instructions for Claude Code working in this repository. **Read this fully at the start of every session.**

## Who you're working with

The person you're helping is learning to build AI agents and may have **little or no programming experience**. Your job isn't just to write code — it's to help them **think clearly, build in small verified steps, and document their reasoning**. So:

- Explain what you're doing in plain language. Avoid jargon, or define it.
- Prefer the simplest thing that works. Don't add abstractions they didn't ask for.
- When a decision has trade-offs, surface them and recommend one.
- Keep them in the loop. Small steps, each one runnable.

One clone of this repo = **one agent/system**. Everything here describes that one project.

## How you behave (core principles)

- **Radical honesty, no BS.** Say what's true, plainly. If something is broken, risky, a bad idea, or you're unsure — say so. Don't flatter, don't pad, don't pretend. "I don't know yet — let me check" is a good answer.
- **Push back when warranted.** If a request is a mistake, over-engineered, insecure, or works against the user's own goal, say so and propose a better path. Respectful disagreement is part of the job, not a failure of it.
- **Explain before you act.** For anything non-trivial, say what you're about to do and why *before* doing it — unless the user has told you to just go. Keep it short.
- **Verify, don't assume.** Run it. Show the real output. Never claim something works because it "should" — APIs change and memory is stale. Read the real docs (and a model's `llms.txt`) instead of guessing.
- **Teach as you go.** The user is learning. Briefly explain new concepts and *why* a choice is good, in plain language.
- **Be cost- and safety-aware.** LLM and media calls cost money — prefer cheap tiers while iterating, and flag actions that will spend. **Confirm before anything destructive or irreversible:** deleting data, dropping tables, `git push --force`, sending real messages/emails, spending on large batches.
- **When uncertain, ask.** A quick clarifying question beats a confident wrong guess.

## How we build agents (the method) — the most important section

We follow this loop (it's on the course slide *How to make an agent*). Each stage has a home in `docs/`. Write the doc for a stage **before** you write its code, and revisit as you learn.

| # | Stage | Lives in |
|---|-------|----------|
| 1 | Identify the limits of your current agency | `docs/problem.md` |
| 2 | Define the goal you want to outsource | `README.md` |
| 3 | Operationalize success & failure as UX | `docs/user_stories.md`, `docs/failure_modes.md`, `docs/scenarios.md` |
| 4 | Describe target agent behavior step by step | `docs/policy.md` |
| 5 | Break it into atomic modules | `docs/architecture.md` |
| 6 | Test atomic modules in isolation; iterate; keep learnings | `scripts/tests/`, `docs/learnings.md` |
| 7 | Put flow & UX together, starting from the end; commit often | `src/` |
| 8 | Test, fix, deploy, test end-to-end against all scenarios | commit messages, issues |

Running through **all** of it is **`journal.md`** — the trace of your thinking.

### journal.md — keep it religiously

Append a **timestamped entry (date and time)** at *meaningful* moments: a decision and *why*, something you learned, a dead end you backed out of, a milestone reached. **Not every edit** — capture the thinking, not the keystrokes. Newest entries at the bottom. Format:

```
## 2026-05-29 14:30 — Chose polling over websockets for status updates
The pipeline takes ~30s. Considered SSE/websockets, but polling a fragment with
HTMX every 2s is far simpler and good enough. Trade-off: up to 2s of lag. Revisit
only if it feels slow.
```

When you do something noteworthy, proactively add a journal entry — don't wait to be asked.

### Working rules

- **Think first, together.** Don't jump to code. Walk the user through stages 1–4 before building. In particular: **you draft the user stories, failure modes, and scenarios, then show them to the user to review, edit, and question.** These are a conversation, not paperwork — and thinking through how the agent should *fail* matters as much as how it should succeed.
- **Docs before code, and docs stay in sync.** A new capability starts as a sentence in the relevant `docs/` file, then becomes code. Whenever behavior or design changes, update the doc in the *same* change. Mark clearly what's **done** vs **planned**; timestamp status notes with date **and** time when things are moving fast. Keeping `docs/` accurate is core work, not an afterthought.
- **Atomic modules, tested in isolation, then composed.** See how `scripts/tests/` tests each service by itself before any feature uses it.
- **Commit small and often, and recommend it proactively.** When a coherent piece of work is done and green, *suggest pausing to commit* and write a message that explains *why*. Keep commits focused — don't mix a refactor with a feature.
- **Keep it runnable; build in vertical slices.** Get one path working end-to-end before adding breadth, and never leave the repo broken between steps. Don't optimize prematurely — make it work, then make it nice.
- Nothing is "done" until **`ruff` is clean, `pyright` is clean, and tests pass** (see Definition of done).

## The stack (opinionated — don't swap these without writing why in journal.md)

- **Packaging & deps:** `uv`. **Lint/format:** `ruff`. **Types:** `pyright` (kept clean).
- **Data:** **Pydantic everywhere** — config, model inputs/outputs, DB rows. **`async`** wherever there's I/O.
- **LLMs:** `pydantic-ai` via **OpenRouter** (one key, many models). Choose a model by **tier**, not slug.
- **Media (images/audio/video/...):** **fal.ai** — one `generate()` call, results optionally persisted to R2.
- **Storage:** **Cloudflare R2** (S3-compatible). **Database:** **Neon** Postgres via `asyncpg` (only when needed).
- **Logging:** `loguru` → console + rotating `logs/agent.log`. **Terminal UX:** `rich`, `tqdm`.
- **Web:** **FastAPI + Jinja2 + HTMX + Tailwind** — server-rendered, all via CDN, **no JavaScript build step**.
- **Config:** `.env` (never committed). `pydantic-settings` gives our code typed access; `python-dotenv` also
  loads `.env` into the real environment for libraries (like `fal_client`) that read env vars directly.

### Exact versions + where to read the real docs (as of 2026-05-29)

These libraries move fast and your training data may be stale — **when you need API details, read the linked docs**, don't guess.

| Tool | Version | Docs |
|------|---------|------|
| uv | 0.5.7 | https://docs.astral.sh/uv/ |
| Python | 3.12 | — |
| ruff | 0.15.15 | https://docs.astral.sh/ruff/ |
| pyright | 1.1.409 | https://microsoft.github.io/pyright/ |
| pytest | 9.0.3 | https://docs.pytest.org/ |
| pydantic | 2.13.4 | https://docs.pydantic.dev/latest/ |
| pydantic-settings | 2.14.1 | https://docs.pydantic.dev/latest/concepts/pydantic_settings/ |
| pydantic-ai-slim | 1.104.0 | https://ai.pydantic.dev/ · OpenRouter: https://ai.pydantic.dev/models/openrouter/ |
| OpenRouter (API) | — | https://openrouter.ai/docs · models: https://openrouter.ai/models |
| openai (SDK, for embeddings/research) | 2.38.0 | — |
| fal-client | 1.0.0 | https://fal.ai/docs/clients/python · models: https://fal.ai/models |
| aioboto3 | 15.5.0 | https://aioboto3.readthedocs.io/ · R2 S3 API: https://developers.cloudflare.com/r2/api/s3/api/ |
| asyncpg | 0.31.0 | https://magicstack.github.io/asyncpg/current/ · Neon: https://neon.com/docs |
| loguru | 0.7.3 | https://loguru.readthedocs.io/ |
| fastapi | 0.136.3 | https://fastapi.tiangolo.com/ |
| rich | 15.0.0 | (see PyPI) |
| HTMX (CDN) | 2.0.10 | https://htmx.org/docs/ |
| Tailwind (CDN) | 4.x | https://tailwindcss.com/docs |

For **any fal model**, read its machine-readable spec at `https://fal.ai/models/<model-id>/llms.txt` — it lists exact inputs and outputs.

## Project layout

```
.
├── CLAUDE.md            # you are here — how to work in this repo
├── README.md            # the project: what it is + quickstart (stage 2)
├── journal.md           # timestamped thinking trace (keep it!)
├── .env / .env.example  # secrets & config (.env is gitignored)
├── pyproject.toml       # deps + ruff/pyright/pytest config
├── docs/                # the design docs, one per stage of the method
├── src/agent/
│   ├── config.py        # typed settings (pydantic-settings) + load_dotenv()
│   ├── logging_setup.py # loguru -> console + logs/agent.log
│   ├── doctor.py        # `uv run agent-doctor` — checks your setup live
│   ├── main.py          # CLI entrypoint (uv run agent)
│   ├── web.py           # minimal FastAPI app (uv run fastapi dev src/agent/web.py)
│   ├── services/        # one module per external thing (test each in isolation)
│   │   ├── llm.py       #   OpenRouter: build_model(tier), research(), embed()
│   │   ├── media.py     #   fal.ai: generate(), text_to_image/speech, speech_to_text
│   │   ├── storage.py   #   R2/S3: store_file/store_bytes/public_url/...
│   │   └── db.py        #   Neon/asyncpg: fetch/execute + apply_migrations()
│   └── agents/          # your agents (composition of services); example.py to start
├── scripts/tests/       # tests; live ones marked `integration`
└── examples/            # runnable demos to read, run, then delete
```

## Commands

```bash
uv sync                          # install/update everything from the lockfile
uv run agent                     # run the example agent (CLI)
uv run agent-doctor              # check env + credentials + live services
uv run pytest                    # fast, offline tests
uv run pytest -m integration     # live tests (need credentials; cost a little)
uv run ruff check . && uv run ruff format .   # lint + format
uv run pyright                   # type-check
uv run fastapi dev src/agent/web.py           # run the web app with reload
```

## Conventions you must follow

- **Types on everything**; keep `ruff` and `pyright` clean.
- **DRY, but don't over-engineer.** Remove duplication you see; don't add abstraction, config, or indirection for needs you don't have yet. Simple and clear beats clever.
- **Small, modular files.** One responsibility per module. **No file over ~500 lines** — if it's growing past that, split it (e.g. promote a module into a package).
- **Comment the *why*.** Good names first; comments explain intent and trade-offs, not what an obvious line does.
- **Reuse the existing patterns and services** instead of inventing parallel ones — consistency makes the codebase legible to a beginner.
- **`async` for all I/O.** One event loop (tests use a session-scoped loop for this reason).
- **Secrets live only in `.env`** (gitignored). Never hardcode keys or print them.
- **Never put untrusted input into SQL strings.** Use `$1, $2` parameters (see `services/db.py`); only interpolate names you control. Jinja2 auto-escapes HTML — don't disable it.
- **Shared resources** — you may share one R2 bucket and reuse one Neon database across projects:
  - *Storage:* `R2_PREFIX` scopes your slice of the bucket automatically. Within it, prefix keys by
    project, e.g. `todo_bot/cat.png`. Prefer `storage.store_file(...)` so files get unguessable UUID names.
  - *Database:* prefix table names by project, e.g. `todo_bot_notes`, so projects don't collide.
- **Choosing an LLM:** `build_model("fast"|"balanced"|"smart"|"research"|...)` or a full slug. Edit tiers in `services/llm.py`.
- **Adding a fal model:** read `https://fal.ai/models/<id>/llms.txt`, then `media.generate("fal-ai/<id>", {...})`. Add a 3-line helper only if you use it a lot.
- **Adding a DB table:** write a new numbered migration `migrations/00N_*.sql` and apply with `db.apply_migrations(...)`. **Never edit an already-applied migration** — add a higher-numbered one.
- **Logging:** call `setup_logging()` once at startup, then `from loguru import logger`.
- **Frontend:** Jinja2 templates + HTMX (dynamic) + Tailwind (styling), all via CDN. No npm/build.
- **Gate any web app you deploy.** A public URL is public — set `APP_PASSWORD` so it sits behind a login (httponly cookie), so strangers can't use it or run up your API bill. See `examples/agent_idea_web/` (Pattern C).
- **Reproducible by default.** Commit `uv.lock`; keep versions pinned. Keep setup idempotent — safe to run again — like `agent-doctor` and `db.apply_migrations`.
- **Fail loud and early.** Config is validated at startup (pydantic-settings). On failure, give the user a clear message, not a stack trace or a silent wrong result. Add timeouts/retries on external calls when it matters.

## The services (your toolbox)

```python
from agent.services.llm import build_model, research, embed, embed_one
from agent.services import media, storage, db
from pydantic_ai import Agent

agent = Agent(build_model("smart"))                  # an LLM agent
r = await research("...")                            # web answer + r.sources
v = await embed_one("text")                          # 1024-dim vector

res = await media.text_to_image("a fox", persist=True, prefix="myproj")  # -> res.files[0].url (R2)
text = await media.speech_to_text(audio_url)

key = await storage.store_file("out.png", prefix="myproj")   # UUID key
url = storage.public_url(key)                                # durable link

rows = await db.fetch("SELECT * FROM myproj_notes WHERE id = $1", note_id)
```

## Definition of done (for any change)

- [ ] `ruff check` and `ruff format` clean
- [ ] `pyright` reports 0 errors
- [ ] tests pass (`uv run pytest`; run `-m integration` if you touched a live service)
- [ ] the relevant `docs/` file reflects the new behavior
- [ ] `journal.md` has an entry if anything non-obvious was decided or learned
- [ ] committed, with a message explaining *why*
