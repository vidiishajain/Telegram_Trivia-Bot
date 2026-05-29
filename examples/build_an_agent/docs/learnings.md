# Learnings

> **Worked example** for the terminal idea generator. (Stage 6: keep what you learn.)

- **Two models beat one here.** Sonar alone gives accurate-but-dry research; Claude alone
  invents plausible-but-stale specifics. Research → design (Sonar → Claude) gives ideas that
  are both *current* and *fun*.
- **`balanced` (Claude Sonnet) is plenty** for the design step — `smart` wasn't worth the
  cost for a short, playful write-up.
- **A typed `output_type` (`AgentIdea`) is what keeps it concrete.** Forcing a `first_step`
  field stops the model from hand-waving.
- **`rich` Markdown** renders the idea beautifully in the terminal with almost no code.
- **Saving by slug of the title** (`fridgeline-chef.md`) is enough — no IDs needed for a
  single-file output.

## Open questions

- Would letting the user pick a tier (fast vs balanced) be worth the added choice? (Probably
  not — defaults are good enough, and choice = friction for a beginner.)
