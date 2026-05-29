# Policy

> **Worked example** for the "agent idea" web app. (Stage 4: behavior, step by step.)

## The agent's job, in one line

Turn a problem + domain of life into a researched, illustrated, shareable agent concept.

## Step by step (the pipeline)

1. User submits a domain → create a row (`status=pending`, `stage=queued`) and start the
   work in the background; redirect to the result page immediately.
2. `stage=researching` — `research()` (Sonar): pains, needs, current tools, **with sources**.
3. `stage=writing` — Claude (`balanced`, typed `IdeaWriteup`): title, plain-prose write-up,
   a concrete "where to start", and an **image prompt** describing a simple labeled diagram.
4. `stage=drawing` — `media.text_to_image(prompt, persist=True)` (nano-banana-2 → R2).
5. `status=done` — save the image URL; the polling page swaps in the final result.

## Tools it can use

- `llm.research()` (Sonar) → step 2 · `build_model("balanced")` + `output_type` → step 3
- `media.text_to_image(..., persist=True)` → step 4 (image to R2)
- `db` (raw SQL + migrations) → the row/state machine throughout

## Tone & rules

Write-ups are warm, vivid, plain prose. The image prompt must be a **schematic diagram**
(boxes/arrows), not a photo. Exactly one idea per submission. The deployed app is always
password-gated.
