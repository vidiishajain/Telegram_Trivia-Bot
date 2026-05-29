# Policy

**Stage 4 — Describe the target agent behavior, step by step.**

This is the agent's "rulebook" — how it should think and act. Most of it becomes the
**system prompt** and the **control flow** in your code. Write it in plain language first.

## The agent's job, in one line

_(e.g. "Help an ear-trained musician name what they're playing and read it back.")_

## Step by step

What does the agent do, in order, for a typical request?

1. ___
2. ___
3. ___

## Tools it can use

_(Which services/tools, and *when* it's allowed to use each.)_
- e.g. `research()` — when the user asks about current/real-world facts
- e.g. `media.text_to_image()` — when a visual would help

## Tone & style

_(How should it sound? Concise? Warm? Never preachy?)_

## Rules & boundaries

_(Pull the hard rules from `failure_modes.md`. What must it always / never do?)_
