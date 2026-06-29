# Agent Starter (Python)

An opinionated, batteries-included starter for building AI agents — from simple scripts to Telegram bots to small web apps. You clone it, point Claude Code at it, and build.

> **One clone = one project.** Starting a new agent? Clone a fresh copy.

---

## ✏️ Your project

**What I'm building:** A Telegram trivia bot with two modes — group competitive play and global solo ranked play — backed by ELO ratings, streaks, head-to-head rivalry records, and seasonal leaderboards with playoffs.

**Who it's for:** Two audiences sharing one bot:
- **Group players** — friend groups who want on-demand trivia battles in their existing Telegram group chat, with group-scoped ELO and rivalries.
- **Solo players** — individuals who DM the bot privately and compete globally against every other solo player on a shared leaderboard.

**What "done" looks like:**

*Group mode:* Someone types `/trivia` in a group chat. The bot posts 6 topic options with tap buttons. First topic to get >50% of the group's votes wins immediately — quiz starts. Five multiple-choice questions appear as one message. Players tap A/B/C/D over a 2-hour window. Results post automatically with ELO deltas and rivalry callouts. Seasons run 30 days, end with a playoff, soft-reset ELO, repeat.

*Solo mode:* A user DMs the bot and presses Start. The bot explains the game and registers them. They type `/play` whenever ready. The bot delivers today's 5 questions one at a time — tap an answer, get instant feedback (correct/wrong + explanation), then the next question. At day's end, ELO updates globally across all solo players who played that day. Same soft-season rhythm as group mode.

---

## Build status

| Phase | What | Status |
|-------|------|--------|
| 0 | Design docs (problem, stories, scenarios, policy, architecture) | ✅ Done |
| 1 | Schema (migrations) + trivia_db.py + tests | ✅ Done — 13/13 tests green |
| 2 | scoring.py + unit tests | ✅ Done — 14/14 tests green |
| 3 | question_generator.py + integration test | ✅ Done — 5/5 tests green |
| 4 | Bot shell — /start, /trivia, /play, voting mechanism | ✅ Done — ruff + pyright clean |
| 5 | Round lifecycle — post → collect answers → score → results | ⬜ Pending |
| 6 | Commands — /leaderboard, /me, /score, /rivalry, /help | ⬜ Pending |
| 7 | Seasons + playoffs + Railway deploy | ⬜ Pending |

---

## Quickstart

**Fork this repo first — don't work in the original.** On GitHub click **Fork**, then clone
*your* fork (if you clone the original, you won't be able to save and push your work):

```bash
git clone https://github.com/<your-username>/agent-starter-python.git
cd agent-starter-python
```

You also need [`uv`](https://docs.astral.sh/uv/) installed (it manages Python and dependencies). Then:

```bash
# 1. Install dependencies (uv reads the lockfile and sets up Python 3.12)
uv sync

# 2. Create your .env and add your keys
cp .env.example .env
#    open .env and fill in OPENROUTER_API_KEY (the others are optional)

# 3. Check everything is wired up
uv run agent-doctor

# 4. Run the example agent
uv run agent
```

`agent-doctor` prints your environment, which credentials are set, and whether the live services respond (it even enables `pgvector` if you've set a database). Green ticks mean you're ready.

## What's in the box

- **LLMs** via OpenRouter — pick a model by *tier* (`fast`, `balanced`, `smart`, `research`), plus embeddings and web research with sources.
- **Media** via fal.ai — generate images/audio/etc. with one call, optionally saved to your storage.
- **Storage** via Cloudflare R2 (S3-compatible) — upload files, get durable links.
- **Database** via Neon Postgres — async, with a tiny built-in migration runner and `pgvector` for embeddings.
- **Logging** to console + `logs/agent.log`, a **doctor** to check your setup, and a clean **CLI** and **web** (FastAPI + HTMX + Tailwind) starting point.

Two runnable demos live in [`examples/`](examples/) — read them, run them, then delete them.
Each is a folder with its own `docs/` showing the method filled in for a real project:
- `examples/build_an_agent/` — a terminal app that suggests an agent for you to build.
- `examples/agent_idea_web/` — a small web app: research → write-up → diagram → saved & shareable.

## How you build (the method)

This starter is built around a specific way of working — think first, document as you go, build and test small pieces, then compose. The full method is in **[CLAUDE.md](CLAUDE.md)** (which also tells Claude how to help you), and each stage has a doc template in **[`docs/`](docs/)**. The single most important habit: keep **[`journal.md`](journal.md)** as you go.

## Common commands

```bash
uv run agent                  # run the example agent
uv run agent-doctor           # check your setup
uv run pytest                 # fast tests
uv run pytest -m integration  # live tests (need credentials)
uv run fastapi dev src/agent/web.py   # run the web app
```

## Configuration

All config is environment variables, loaded from `.env` (never commit it). See `.env.example` for every option. Only `OPENROUTER_API_KEY` is required; add the rest when a project needs media, storage, or a database.
