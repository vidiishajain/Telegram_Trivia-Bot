# Failure Modes

**Stage 3 — Operationalize *failure* as UX.**

Agents fail in ways normal programs don't: they make things up, misread intent, call
the wrong tool, or cost money/time. Decide *now* what failure looks like and how the
agent should fail **gracefully** instead of confidently-wrong.

## For each likely failure

| What could go wrong | How likely / how bad | How the agent should handle it |
|---------------------|----------------------|--------------------------------|
| e.g. the model invents a fact | medium / bad | cite sources; say "I'm not sure" when unsupported |
| e.g. the user's input is vague | high / mild | ask one clarifying question |
| e.g. an external API is down | low / bad | catch the error, tell the user plainly, log it |

## Hard rules (things the agent must never do)

- _(e.g. never delete data without confirmation)_
- _(e.g. never claim certainty it doesn't have)_

## What the user should see when things go wrong

_(A friendly, honest message beats a stack trace or a confident lie.)_
