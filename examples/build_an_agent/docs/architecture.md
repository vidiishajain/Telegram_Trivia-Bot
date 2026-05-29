# Architecture

> **Worked example** for the terminal idea generator. (Stage 5: atomic modules.)

A tiny pipeline of independent steps, all in `main.py` (small enough for one file).

| Module (function) | Does one thing | In → Out |
|---|---|---|
| `dream_up_idea` → research call | get current context on the topic | topic → research text |
| `dream_up_idea` → design call | propose a structured idea | topic + research → `AgentIdea` |
| `to_markdown` | format the idea as Markdown | `AgentIdea` → markdown string |
| `slugify` + save | persist it | title → `ideas/<slug>.md` |

## Starter services used

- `llm` — `research()` (Sonar) for context, `build_model("balanced")` for the typed idea.
- media / storage / db — **not used** (this agent only thinks and writes a local file).

## Data flow

```
user text → research(topic) ─┐
                             ├→ Claude (output_type=AgentIdea) → render (rich) + save (.md)
        (research context) ──┘
```

## Data stored

Just a Markdown file per idea under `ideas/` (gitignored). No database.
