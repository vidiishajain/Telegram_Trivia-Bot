# Architecture

> **Worked example** for the "agent idea" web app. (Stage 5: atomic modules.)

| Module (in `app.py`) | Does one thing | In → Out |
|---|---|---|
| `research_*` (via `llm.research`) | web research + sources | domain → text + sources |
| `write_idea` | structured write-up + image prompt | domain + research → `IdeaWriteup` |
| `media.text_to_image(persist=True)` | diagram → R2 | prompt → durable image URL |
| `create_idea` / `update_idea` / `get_idea` | the row state machine | SQL ↔ `AgentIdea` |
| `run_pipeline` | composes the above, updating `stage` | (id, domain) → updates row |
| routes + templates + HTMX | submit, poll, render | HTTP ↔ HTML |

Each `services/` piece was tested in isolation first (`scripts/tests/`); this app is the
composition.

## Starter services used

`llm` (research + balanced/typed) · `media` (fal, persist to R2) · `storage` (R2, via persist) ·
`db` (Neon, raw SQL + `apply_migrations`).

## Data flow

```
submit → row(pending) ─┐                      ┌────────── HTMX polls /fragment every 2s
                       ▼ (background task)     │  pending → show stage;  done → final HTML (stop)
   research → write → image (→R2) → row(done) ─┘
```

## Data stored

One table, `agent_ideas` (raw SQL, mapped to the `AgentIdea` Pydantic model). Schema evolves
via **forward-only migrations**: `001_create_agent_ideas.sql`, then `002_add_research_sources.sql`
(adds a `sources jsonb` column). State columns: `status`, `stage`; content columns: `title`,
`research`, `writeup`, `where_to_start`, `image_prompt`, `image_url`, `sources`, `error`.
