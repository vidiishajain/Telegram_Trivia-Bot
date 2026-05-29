# Architecture

**Stage 5 — Break it into atomic modules.**

Decompose the agent into the smallest pieces you can build and **test in isolation**
(stage 6). Each piece should do one thing. Then you'll compose them (stage 7).

## The pieces

List each atomic module: what it does, what goes in, what comes out.

| Module | Does one thing | Input → Output |
|--------|----------------|----------------|
| e.g. `transcribe` | turn audio into notes | audio url → list of notes |
| e.g. `analyze` | label key & chords | notes → analysis (typed) |
| ... | | |

## Which starter services does each use?

- `llm` (chat / `research()` / `embed()`) — for: ___
- `media` (fal) — for: ___
- `storage` (R2) — for: ___
- `db` (Neon) — for: ___

## Data flow

_(Sketch how data moves from the user through the modules and back. A few arrows in
text is fine: `input → module A → module B → output`.)_

## Data you store (if any)

_(Tables and their columns. Remember: one numbered migration per change; prefix table
names with your project. See CLAUDE.md.)_
