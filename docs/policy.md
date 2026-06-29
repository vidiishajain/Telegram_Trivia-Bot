# Policy

**Stage 4 — Describe the target agent behavior, step by step.**

## The bot's job, in one line

Run a daily group trivia tournament with a long memory, surfacing rivalries and season standings automatically — no human administration required.

---

## Scheduled behaviors (no user input required)

### Daily quiz delivery (9:00am UTC)
1. Generate a fresh daily theme (check last 14 themes in DB, avoid repeats).
2. Generate 5 multiple-choice questions for that theme via LLM. Validate each question has: text, choices A–D, correct choice (one of A/B/C/D), explanation.
3. If generation fails or validation fails: retry once. If still failing: log error, DM admin, skip today.
4. Create a `trivia_round` record (status=`open`, `closes_at = now + ANSWER_WINDOW_MINUTES`).
5. Save 5 `trivia_questions` records linked to the round.
6. Post formatted quiz to the group with inline A/B/C/D buttons per question.
7. Save the Telegram `message_id` on the round record.

### Round scoring (every 60 seconds — checks for expired open rounds)
1. Query for any round where `status = 'open'` and `closes_at <= now()`.
2. If none found: stop.
3. For each expired round:
   a. Set status = `closed` (prevents double-scoring).
   b. Fetch all answers for the round.
   c. Compute per-player scores (count correct answers).
   d. Compute ELO deltas via pairwise decomposition (see ELO section in architecture).
   e. In a single DB transaction: save `trivia_round_scores`, update `trivia_players.elo`, insert `trivia_elo_history` rows, upsert `trivia_rivalries` for all pairs, update streaks (increment if answered, reset to 0 if absent).
   f. Set round status = `scored`.
   g. Build results message: ranked list with scores and ELO deltas, rivalry callouts, streak announcements, correct answers + explanations.
   h. Post results to the group.

### Season end check (daily, after quiz delivery)
1. Check if active season's `ended_at` date has passed.
2. If yes: post final season leaderboard, apply soft ELO reset (pull 50% toward 1200), record in `trivia_elo_history` with `reason='season_reset'`, seed playoff bracket from top N players, start next season.

---

## Commands

### `/join` (any user)
1. Check if the sender already has a `trivia_players` row. If yes: "You're already in! Type /me for your stats."
2. If no: create player (ELO=1200, streak=0). Welcome them and explain the game. Tell them the next quiz time.

### `/score` (during an open round)
1. Find the active open round.
2. Show who has answered so far (names only — no answers revealed).
3. Show time remaining until window closes.
4. If no open round: show yesterday's results summary and next quiz time.

### `/leaderboard`
1. Show the current season's standings: rank, name, ELO, rounds played, current streak.
2. Top 10 players. If more than 10 are registered, note "Type /leaderboard full for all."
3. Highlight the user's own row.

### `/me`
1. Show personal stats: ELO, season rank, streak, best streak, accuracy (% correct), rounds played.
2. Show head-to-head records with each opponent: W–L–T and a brief label (dominant / rival / even / underdog).

### `/rivalry`
1. Show head-to-head records for the user against all opponents they've played.
2. Highlight the most dramatic one ("You've lost to Alex 5 in a row — that's a grudge match.").

### `/help`
1. List all commands with one-line descriptions.
2. Explain the ELO system briefly: "Higher score vs harder opponents = bigger ELO gain."

### Admin only: `/forcescore` (admin Telegram IDs in config)
1. Immediately close and score the current open round, regardless of `closes_at`.
2. Useful for testing or recovering from a scheduling failure.

### Admin only: `/newseason`
1. Manually end the current season and start a new one.
2. Prompts for confirmation before acting.

---

## Answer collection

- Players tap inline buttons (A/B/C/D) directly on the quiz message.
- Each button tap records one answer for that question. The bot acknowledges with a brief private reply: "Got it — Q3: C ✓ recorded."
- Players can change their answer before the window closes — only the **last tap per question** counts. (The unique constraint + upsert handles this.)
- The bot never reveals whether the answer is correct until the round closes.
- After the window closes, tapping any button triggers the "round is closed" message.

---

## Tone & style

- **Warm and punchy, not corporate.** This is a friend group — the bot can have personality.
- **Rivalry callouts should sting a little, but never be mean.** "Redemption pending" not "you're losing badly."
- **Results messages should be scannable.** Rank, name, score, ELO delta — all on one line per player.
- **Explanations should be interesting**, not just "the correct answer is X." The LLM should write something you'd actually want to read.
- **Never be wordy in a command reply.** `/me` response should fit in one Telegram message without scrolling.

---

## Rules the bot must never break

- Never reveal correct answers before a round closes.
- Never apply partial ELO updates — atomic transaction or nothing.
- Never silently ignore an error — log it, DM admin if it affects the game.
- Never score an already-scored round (check status before scoring).
- Never register the same player twice (upsert on `telegram_id`).
