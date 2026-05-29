# Learnings

> **Worked example** for the "agent idea" web app. (Stage 6 — real things we hit building
> and deploying this. These are the bugs and gotchas, kept so you don't repeat them.)

- **Long work needs the async-job + poll pattern.** A 30s pipeline can't ride one HTTP
  request. A `status`/`stage` column + background task + an HTMX poll that *stops itself*
  when done is the reusable shape (see the repo's `examples/README.md`, Pattern B).
- **`sources` (jsonb) is NULL on a fresh row → the page crashed.** `AgentIdea.sources` is a
  non-optional list, so loading the page in the first seconds (before research ran) raised a
  validation error. Fix: normalize NULL → `[]` in `get_idea`. **Lesson: test the *first*
  page load, not just the finished result** — our happy-path test masked this.
- **Perplexity sources live in `message.annotations[].url_citation`** (url + title), not a
  top-level `citations` field, and pydantic-ai's `Agent` hides them — so `llm.research()`
  calls OpenRouter directly to capture them.
- **Deploy gotcha: `$PORT` in the start command doesn't expand** — Railway runs it without a
  shell. `fastapi run` reads the `PORT` env var itself, so pass no `--port`. The `railway logs`
  traceback told us this immediately (read the logs, don't guess).
- **`nano-banana-2` makes clean labeled diagrams** when prompted for a "schematic, boxes and
  arrows, not a photo," and `persist=True` gives a durable R2 URL safe to store in the DB.
- **Plain prose beats markdown** for the write-up, since we render it directly (no markdown
  parser) — we instruct the model accordingly.

## Open questions

- Should old `pending` rows that never finished (e.g. a crash mid-pipeline) be swept/expired?
- Worth caching identical domains to avoid re-spending on research + image?
