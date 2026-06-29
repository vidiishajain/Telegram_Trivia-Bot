# Journal

This is the running trace of your thinking as you build. It's the most important
document in the project — more than any single piece of code.

**How to use it**
- Add an entry at *meaningful* moments: a decision (and **why**), something you
  learned, a dead end you backed out of, a milestone reached.
- **Not** every edit. Capture the thinking, not the keystrokes.
- Always **timestamp** with date **and** time. Newest entries go at the bottom.
- Both you and Claude should add entries.

Format:

```
## YYYY-MM-DD HH:MM — Short title
What you were trying to do, what you decided, and why. What you learned.
```

---

## 2026-05-29 12:00 — Project initialized from the agent starter
Cloned the starter. Next: fill in `docs/problem.md` (what can't I do today?) and the
"Your project" section of `README.md` (what am I building?). Then design before coding.

## 2026-06-22 — Chose the project: Trivia Tournament with Rivals (Telegram bot)
Decided to build a daily themed trivia quiz bot for a Telegram friend group. The core motivation is twofold: (1) it's genuinely fun and has real social stakes, and (2) it teaches databases the right way — through necessity. ELO ratings, rivalries, streaks, and seasons *cannot* live in memory; they have to survive restarts and redeploys.

Key architecture decisions made today:
- **aiogram v3** over python-telegram-bot: built async-first, plays well with asyncpg on the same event loop, cleaner Router system for splitting handlers.
- **Inline A/B/C/D buttons** (not typed text replies): frictionless on mobile, unambiguous to score.
- **Pairwise ELO decomposition**: standard chess ELO doesn't work for multiplayer; we generate all C(N,2) virtual 1v1 matches per round. Absence = no penalty (zero ELO change, not a loss).
- **Pre-aggregated rivalries** in `trivia_rivalries`: O(1) lookup vs full table scan every time we need callout data.
- **APScheduler AsyncIOScheduler**: cron jobs on the same event loop as the bot, no threading complications.
- **9 tables**: seasons, players, rounds, questions, answers, round_scores, elo_history, rivalries, playoffs. All prefixed `trivia_`. Applied via the existing `db.apply_migrations()` system.

Phase 0 (docs) is complete. Next: Phase 1 — write all 10 migration SQL files and `trivia_db.py`.

## 2026-06-27 — Redesigned for two modes + group topic voting

After thinking through the user journey, the bot now has two distinct modes in one binary:

**Group mode** — `/trivia` in any group chat starts a topic vote. Players tap their preferred topic (6 options). First topic to get >50% of the group's registered players wins immediately. Quiz starts with that topic. If no majority after 5 minutes, top-voted topic wins. No more hardcoded `TELEGRAM_GROUP_ID`.

**Solo mode** — user DMs the bot, presses Start, types `/play`. Questions delivered one at a time with instant answer feedback (can reveal immediately since no other players to copy from). ELO is global across all solo players.

**Schema changes made (all migrations were untracked so rewritten cleanly):**
- `trivia_seasons`: added `chat_id` (0 = global solo season)
- `trivia_players`: changed from `id BIGINT PK` to `id SERIAL PK` + `telegram_id BIGINT` + `chat_id BIGINT`. UNIQUE(telegram_id, chat_id). Same person can have a solo row (chat_id=0) and per-group rows.
- `trivia_rounds`: added `chat_id`, `mode` ('group'|'solo'), `topic_vote_ends_at`. Status now starts at 'voting' for group rounds, 'open' for solo.
- New table `trivia_topic_votes`: one row per (round, player) vote during the voting phase.
- All FK references to `trivia_players.id` fixed from BIGINT → INTEGER.
- Removed `telegram_group_id` from config.py — no longer needed.
- Added `trivia_vote_window_minutes` (default 5) and `trivia_min_solo_window_minutes` (default 30) to config.

**Why chat_id=0 for solo instead of NULL?** NULL values don't satisfy UNIQUE constraints in Postgres — two NULLs are considered distinct, which would allow duplicate solo players. Using 0 as a sentinel gives clean UNIQUE(telegram_id, chat_id) enforcement.

Phase 1 in progress: schema is done. Next: run migrations, write and run trivia_db tests, then scoring.py.

## 2026-06-27 — Phases 1–3 complete, all tests green

- Phase 1 (DB): 13/13 integration tests passing. Key fix: migration 010 (indexes) originally referenced `trivia_topic_votes` before migration 011 created it — moved the index into 011 alongside the table definition. Rule: index lives in the same migration as the table.
- Phase 2 (Scoring): 14/14 unit tests passing in 0.01s. Already complete from earlier work.
- Phase 3 (Question generator): 5/5 integration tests passing. LLM returns well-structured questions with strong explanations on first attempt — no prompt tuning needed.

Next: Phase 4 — bot shell. Need to install aiogram, wire up /start (solo), /trivia (group vote), /play (solo), and the voting callback handler.

## 2026-06-27 — Phase 4 complete: bot shell live

Added aiogram 3.29.0 + apscheduler 3.11.2. Built three files:
- `services/telegram.py` — bot singleton, keyboard builders, message formatters
- `agents/trivia_bot.py` — all routers: /start, /play, /trivia, /score, /leaderboard, /me, /help + solo and group answer callbacks + topic vote callback
- `scheduler.py` — two APScheduler jobs running every 60s: vote resolver + round scorer

Bot started successfully locally: migrations applied, scheduler up, polling active.

Key decisions:
- `_SOLO_CHAT_ID = 0` as sentinel in all DB calls for solo mode
- Solo questions delivered one-at-a-time with instant feedback; group questions in one message with button grid
- Voting callback fires `_start_round_with_topic()` immediately on majority — no polling needed
- Scheduler handles the timeout fallback (force-picks highest-voted topic if no majority by `topic_vote_ends_at`)
- `isinstance(callback.message, Message)` guard needed because aiogram types `callback.message` as `MaybeInaccessibleMessage`

Phase 5 next: end-to-end testing against all scenarios. Run `uv run agent` and put the bot through its paces.

## 2026-06-27 — Phase 5 complete: full bot tested and hardened

Extensive end-to-end testing revealed and fixed several bugs, plus a full round of UX enhancements. Key decisions made:

**Bug fixes:**
- **Two bot instances conflict**: `pgrep -f "uv run agent"` + kill before restart is the pattern. Telegram throws 409 Conflict when two pollers hit the same token.
- **"already played" showed even after finishing**: `cmd_play` compared answer count vs question count to distinguish "in progress" vs "done today".
- **Topic vote first-voter bug**: New groups had 1 registered player → 1 vote = 100% = instant majority. Fixed with `max(registered_players, total_votes)` denominator and min-2 guard. Crucial invariant: majority requires at least 2 votes to prevent single-person hijacking.
- **Early close fires after one player answers**: Was checking "returning players" — all had `total_rounds=0` in a fresh group. Switched to topic voters as the expected set — anyone who voted is committed to play all questions.
- **Circular import for rivalry tease**: `scheduler.py` can't import from `trivia_bot.py`. Moved `get_rivalry_tease_line()` into `trivia_db.py` so both files can use it.

**UX enhancements shipped:**
1. **Topic header images** — picsum.photos seeded URLs per topic (stable, no API needed). Sent as `send_photo` before quiz message.
2. **Live rank during solo play** — shows current ELO rank after each answer (not updated until scoring runs, clearly labeled "current rank").
3. **Midnight solo DM** — `_send_solo_recap` DMs solo players their final score/ELO/rank/streak after `job_score_expired_rounds` closes their round.
4. **Pin/unpin quiz message** — bot pins the quiz when it starts and unpins when round closes. Uses `contextlib.suppress(Exception)` so missing permissions don't crash the round.
5. **Button feedback via `show_alert=True`** — group answer callbacks show per-player popup "Q3 → B locked in ✅" before dismissing, since buttons are shared (can't hide per-user).
6. **Progress messages** — when a group player finishes all questions, bot sends "⚡ {name} just submitted!" in the group. If all players done, early-closes and scores.
7. **Rivalry callouts** — after group results, posts up to 3 head-to-head rivalry lines sorted by closeness (ties first). Only shown when ≥ 2 rounds of history exist.
8. **Pre-game rivalry tease** — before quiz starts, if top-2 topic voters have a rivalry, posts a one-liner teasing them.
9. **`/score` with @mentions** — shows Done/In Progress/Still Waiting buckets using `tg://user?id=` inline mention links so players can tap to ping stragglers.
10. **Question difficulty ramp** — pydantic-ai prompt now explicitly asks for Q1-Q2 easy, Q3 medium, Q4-Q5 hard (difficulty field 1-3 on `QuizQuestion`).
11. **Daily streak warning** — `job_streak_warning` cron at 15:00 UTC DMs solo players with streak ≥ 3 who haven't played today. `get_at_risk_solo_players()` in trivia_db.py.

**Architecture note on registration in group mode:** Players register implicitly when they cast a topic vote (`cb_topic_vote` calls `_get_or_register_player`). This is the "I'm in" signal — no separate `/join` command needed. Topic voters become the expected set for early-close detection. Non-voters who answer are bonuses but don't block early close.

All features are ruff-clean and pyright-clean. Bot is ready for production deployment to Railway.

## 2026-06-28 — GIFs, practice mode, /funfacts, bot command menu

Shipped a batch of enhancements. All ruff-clean, pyright-clean, 21 tests passing.

**GIF support (replacing static picsum images):**
- Added `GIPHY_API_KEY` to `Settings` and `.env.example`. Key is optional — bot falls back to text when absent.
- `get_gif_url(query)` in `telegram.py`: calls Giphy search API, picks randomly from top 5 results, returns the original GIF URL. Uses `httpx.AsyncClient` with 5s timeout; returns `None` on any failure.
- Replaced `TOPIC_IMAGES` dict and `CELEBRATION_IMAGE` with `TOPIC_GIF_QUERIES`, `CELEBRATION_GIF_QUERY`, `FUN_FACTS_GIF_QUERY`. All `send_photo` calls replaced with `send_animation` wrapped in `contextlib.suppress` so a failed GIF send never breaks the flow.

**Practice mode (migration 013):**
- Added `'practice'` to the `valid_mode` DB constraint.
- `cb_practice_start` handler triggered by `practice_start` callback: creates a `mode='practice'` round (chat_id=user.id, 1h window), generates a surprise theme, fires questions. No ELO impact — `_score_round` forces `skip_elo=True` when `round_.mode == "practice"`.
- `_send_practice_question` / `cb_practice_answer` mirror the solo flow but use `prac:` prefix in callback data.
- "Play another round" `InlineKeyboardButton` appended after solo quiz completion and after the midnight ELO recap DM, using `practice_start` callback.

**/funfacts command:**
- `generate_fun_facts(topic)` in `question_generator.py`: uses `fast` model, `FunFacts` pydantic output type, generates 5 punchy facts.
- `cmd_funfacts` shows topic picker; `cb_funfacts_topic` generates and posts facts with a matching GIF.
- Added to bot command menus for both DM and group scopes.

**Bot command menu (main.py):**
- `set_my_commands` called at startup for `BotCommandScopeAllPrivateChats` and `BotCommandScopeAllGroupChats`.
- `_maybe_set_bot_photo` generates a mascot avatar via fal-ai/flux/schnell on first run (marker file at `/tmp/.triviabot_photo_set` prevents regeneration). Uses `asyncio.to_thread` for the synchronous fal_client.run call and for pathlib marker checks (ASYNC240 compliance). Correct API is `set_my_profile_photo(InputProfilePhotoStatic(photo=...))` — not `set_my_photo`.

## 2026-06-28 — Fixed 8 reliability bugs in trivia_bot.py / scheduler.py / telegram.py

Bug fixes applied (all ruff + pyright clean):

1. **Silent crash on question generation failure** — wrapped all `generate_questions()` calls in try/except in `cb_solo_topic`, `cb_practice_start`, `_start_round_with_topic`, and `_resolve_vote`. On failure: close the round and tell the user to try again.

2. **Fun facts GIF caption over 1024 chars** — `cb_funfacts_topic` now checks `len(text) <= 950` before using text as caption; if too long, sends a short caption on the GIF and the full facts as a follow-up text message.

3. **GIF send failure swallowed silently** — replaced all `contextlib.suppress` on `send_animation` with explicit try/except that falls through to a text fallback. Affected: `cb_solo_topic`, `cb_solo_answer`, `cb_practice_start`, `cb_practice_answer`, `_start_round_with_topic`, `_resolve_vote`.

4. **Midnight scorer penalises unfinished solo players** — `_score_round` now computes `did_finish = len(player_answers) >= len(questions)` and passes it to `_send_solo_recap`. That function adds a "(⏰ time ran out)" note on the score line and swaps the closing message for "Ran out of time — tomorrow's a fresh start."

5. **Vote resolution fires twice on restart** — `_resolve_vote` now checks `get_round_questions` at entry; if questions already exist the round was already resolved and we log + return early.

6. **Mid-practice `/play` starts a real round on top of practice** — `cmd_play` now closes any open practice round before the topic picker, with a message: "Closing your practice round — let's start the real thing!"

7. **Practice rounds pile up on repeated "Play again" taps** — `cb_practice_start` now closes any existing open practice round before creating a new one.

8. **"Solo effort" message appears in group context** — `format_results_message` in `telegram.py` gained a `mode: str = "group"` parameter. When `skipped=True` in solo/practice mode the message now reads "ELO updates when there's someone to compete against" instead of the group-centric "drag someone in" phrasing. All callers in `scheduler.py` updated to pass `mode=round_.mode`.

## 2026-06-29 — Fixed silent dice + audio failures

User tested and saw neither dice animations nor audio clips. Root cause: two separate failures, both silently swallowed by `contextlib.suppress(Exception)`:

1. **Dice**: All dice sends were wrapped in `contextlib.suppress` with no logging. Changed to try/except with `logger.warning` so failures are visible in Railway logs.

2. **Audio**: `send_voice` requires OGG/OPUS format, but `fal-ai/kokoro` outputs MP3. Telegram rejects it silently. Fixed by:
   - Changing `get_hype_audio` to download the audio bytes (via httpx) instead of just caching the URL
   - Return type changed from `str | None` to `bytes | None`
   - All call sites changed from `send_voice(voice=url)` to `send_audio(audio=BufferedInputFile(bytes, "quiz.mp3"))`
   - `send_audio` accepts MP3; the audio shows as a music player bubble rather than a voice message, which is fine for hype clips

Lesson: never use `contextlib.suppress` on media sends — these need logging so failures are diagnosable. Only use suppress on truly unimportant secondary actions (e.g., pinning a message).
