# Failure Modes

> **Worked example** for the "agent idea" web app. (Stage 3: failure as UX.)

| What could go wrong | Likely / bad | How we handle it |
|---|---|---|
| Pipeline takes ~30s — request would time out | high / bad | Run it as a **background job**; the page polls for status and shows live progress (never one long blocking request) |
| A step fails (model/image/network) | medium / bad | Pipeline catches it, sets `status='error'` + a message; the page shows a friendly error, not a hang |
| Page loaded **before** the pipeline fills fields | high / bad | Render from the row's current state; a fresh row's `sources` is NULL → normalize to `[]` (we hit this exact bug — see learnings) |
| Deployed app is public and open | high / bad | `APP_PASSWORD` gate (httponly cookie) — strangers can't use it or spend your credits |
| Image generation costs add up | medium / mild | One image per submission; documented as a real (small) per-run cost |

## Hard rules

- Never block the web request on the long pipeline.
- Never render a half-built row as if it failed — show progress while `status='pending'`.
- Never deploy this without `APP_PASSWORD` set.

## What the user sees on failure

A short "😬 Something went wrong: <reason>" with a link to try again — and the polling stops.
