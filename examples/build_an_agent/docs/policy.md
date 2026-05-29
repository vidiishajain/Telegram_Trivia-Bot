# Policy

> **Worked example** for the terminal idea generator. (Stage 4: behavior, step by step.)

## The agent's job, in one line

Turn a beginner's rough interest into one fun, concrete, buildable agent idea.

## Step by step

1. Ask the user what kind of agent they'd like to build (one free-text line).
2. **Research** the topic with the `research` tier (Perplexity Sonar) — get current, concrete
   context and examples (~200 words).
3. **Design** with the `balanced` tier (Claude), forcing a typed `AgentIdea` output:
   title, one-liner, why it's fun, what it does, services to use, first step.
4. **Render** it nicely in the terminal (rich) and **save** it as Markdown under `ideas/`.

## Tools it can use

- `llm.research(...)` — step 2 (web-grounded context).
- `build_model("balanced")` with `output_type=AgentIdea` — step 3 (structured design).
- No media/storage/db needed — this agent only thinks and writes a file.

## Tone & rules

Witty, warm, encouraging — never corporate. Exactly **one** idea. It must be buildable with
this starter's services, with a concrete first step the user could do today.
