# Scenarios

> **Worked example** for the "agent idea" web app. (Stage 3: concrete walkthroughs.)

## Happy path

1. Visitor opens the app, logs in with the password.
2. Enters: `helping new parents survive the first 90 days with a newborn`, hits Generate.
3. Redirected to `/agentidea/{id}`; sees live stages: 🔬 Researching → ✍️ Writing → 🎨 Drawing.
4. After ~30s the page shows: a titled idea, a generated diagram, a write-up, "✨ here's
   where you start", and a Sources list (clickable, from the research).

**Expected:** a complete, illustrated, shareable idea page; the diagram URL is a durable
`files.<domain>/.../<uuid>.png`; polling has stopped.

## Edge cases

- **Reload mid-run** → expected: the page shows the current stage and keeps polling (no error).
- **A pipeline step throws** → expected: page flips to a friendly error with a "try again" link.
- **Unknown id** (`/agentidea/nope`) → expected: 404 "Not found", not a crash.
- **No cookie / wrong password** → expected: redirected to `/login`.
