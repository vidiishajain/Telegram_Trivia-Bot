# Failure Modes

> **Worked example** for the terminal idea generator. (Stage 3: failure as UX.)

| What could go wrong | Likely / bad | How we handle it |
|---|---|---|
| Idea is too vague or not actually buildable | medium / bad | System prompt demands ONE concrete idea, doable with the starter's services; structured output (`AgentIdea`) forces a first step |
| User input is empty or gibberish | medium / mild | Still produce a playful idea; the model treats it as a loose theme |
| Research (Sonar) returns little | low / mild | The write-up step still runs from the model's own knowledge — research only enriches it |
| OpenRouter key missing / invalid | low / bad | Fails fast at startup (settings) or on the call; clear error, not a silent hang |

## Hard rules

- Never propose something that needs tools we don't have — keep it to LLM / media / storage / db.
- Keep it to **one** idea (more = decision paralysis, the exact problem we're solving).

## What the user sees on failure

A plain error message (e.g. "OpenRouter rejected the key — check OPENROUTER_API_KEY"),
never a raw traceback dumped as the "answer."
