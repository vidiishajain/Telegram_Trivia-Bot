# Failure Modes

**Stage 3 — Operationalize *failure* as UX.**

For a trivia bot, failure splits into three categories: LLM failures (bad questions), system failures (API/DB down), and game-logic edge cases (weird player behaviour). All three need graceful handling — a silent failure or confident wrong answer is worse than an honest "something went wrong."

## Failure table

| What could go wrong | Likely / bad | How to handle it |
|---------------------|--------------|------------------|
| LLM generates a malformed question (missing choice, wrong JSON structure) | medium / medium | Validate `QuizQuestion` with Pydantic before saving. Retry generation once. If still malformed, skip that question and generate a replacement. |
| LLM generates a question with a wrong correct answer | low / bad | Include the LLM's explanation in the results message so players can see the reasoning. Add `/report` command later if needed. |
| LLM generates a duplicate theme two days in a row | low / low | Keep a rolling log of last 14 themes in DB; pass them to the prompt as "avoid these." |
| Telegram API is down when quiz should post | low / bad | Retry 3× with exponential backoff. If all fail, log the error, mark round as `failed` in DB, DM the admin. |
| Telegram API is down when results should post | low / bad | Same retry strategy. Results data is already in DB — results message can be re-sent manually via `/forcescore`. |
| Database write fails during scoring (ELO update) | very low / very bad | Wrap all scoring writes in a single transaction. On failure: rollback, leave round in `closed` (not `scored`) status, log error, DM admin. Round can be re-scored safely since transaction is atomic. |
| Player taps a button after the answer window closes | high / low | Bot acknowledges: "⏰ This round is closed. Results were posted — tap /score to see them." No answer recorded. |
| Player tries to answer the same question twice | medium / low | Unique constraint on `(question_id, player_id)` catches this at the DB layer. Bot replies: "You already answered this one." |
| Only one player answers a round | medium / low | Score the round normally (1/5 or whatever they got). No ELO changes (zero pairwise matches). Results message notes "Solo round — no ELO changes." |
| Player leaves the Telegram group | low / low | Mark `is_active = false` in `trivia_players`. Exclude from future scoring and leaderboards. Old records preserved for history. |
| New player /join mid-active-round | medium / low | Register them. Tell them the current round is underway and they can start playing next round. Don't let them join a round that's already open. |
| Bot restarts mid-round (Railway redeploy) | medium / medium | On startup: call `apply_migrations()`, then check for any `open` rounds — if `closes_at` has passed, score them immediately. APScheduler re-registers all jobs. State is in Postgres, not in memory. |
| APScheduler job fires twice (edge case with redeploy timing) | low / medium | Check round status before acting: if already `scored`, skip. Idempotency is built into every job. |
| OpenRouter API is down (question generation fails) | low / bad | Retry 3× with backoff. If all fail, skip today's round, log the error, DM admin: "Today's quiz couldn't be generated." |
| Group admin removes bot from group | low / bad | Bot will error on all Telegram API calls to that group. Log it clearly. Don't crash silently. |

## Hard rules (things the bot must never do)

- **Never reveal correct answers before the round closes.** Not in a reply, not in a DM, not in any message.
- **Never apply partial ELO updates.** All ELO changes for a round go in one transaction — all succeed or all fail.
- **Never silently drop an error.** Every failure gets logged (loguru → `logs/agent.log`). Anything that affects the game also gets a DM to the admin.
- **Never let a round get stuck in `open` forever.** The 60-second scheduler job is the safety net: if `closes_at` has passed and status is still `open`, score it.
- **Never show one player's answers to another player** during an open round (e.g. in response to `/score`).

## What players see when things go wrong

- **Quiz didn't post:** Nothing (they don't know). Admin gets a DM.
- **Results late:** Nothing unusual; the scheduler retries. If manual intervention needed, admin types `/forcescore`.
- **Answer rejected (window closed):** "⏰ This round is closed. Results were posted — tap /score to see them."
- **Double answer attempt:** "You already answered Q3. Your original answer stands."
- **Bot is down entirely:** Telegram shows the bot as offline. Players will notice and ping the admin.
