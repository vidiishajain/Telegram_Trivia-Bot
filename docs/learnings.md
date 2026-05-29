# Learnings

**Stage 6 — Test atomic modules in isolation. Iterate. Keep learnings.**

As you build and test each module on its own, write down what you discover: which
prompt phrasing worked, which model/tier was good enough, surprising failures, costs,
quirks of a service. This saves you (and Claude) from re-learning the same things.

`journal.md` is the *chronological* trace; this file is the *distilled* "here's what we
know now" — keep it tidy and current.

## What we've learned

- **LLM / prompts:** _(e.g. "balanced tier handles the analysis fine; fast tier mislabels keys")_
- **Models & tiers:** _(which tier for which step, and why)_
- **Media (fal):** _(which model, what inputs matter, typical latency/cost)_
- **Storage / DB:** _(gotchas, naming, what worked)_
- **Surprises / dead ends:** _(things that didn't work, so you don't retry them)_

## Open questions

_(Things you still need to figure out.)_
