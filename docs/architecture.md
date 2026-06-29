# Architecture

**Stage 5 — Break it into atomic modules.**

See `plan` at `/Users/vidishajain/.claude/plans/yes-i-am-thinking-indexed-widget.md` for full detail. This file is the working reference.

---

## Modules

| Module | Does one thing | Input → Output |
|--------|----------------|----------------|
| `services/question_generator.py` | LLM → typed trivia questions | `theme: str, count: int` → `list[QuizQuestion]` |
| `services/scoring.py` | Pure ELO math, no I/O | `list[PlayerScore]` → `list[ELOUpdate]` |
| `services/rivalry.py` | Detect notable rivalries from records | `list[Rivalry]` → `list[RivalryCallout]` |
| `services/trivia_db.py` | All trivia-domain DB queries | various → typed Pydantic models |
| `services/telegram.py` | Bot singleton + message-sending helpers | round/score data → Telegram messages |
| `agents/trivia_bot.py` | aiogram router — command handlers | Telegram events → DB calls + replies |
| `scheduler.py` | APScheduler jobs — scheduled behaviors | time events → job functions |

---

## Which services each module uses

- `question_generator.py` — `llm.build_model("balanced")` via pydantic-ai
- `scoring.py` — pure Python only, no services (unit-testable offline)
- `rivalry.py` — pure Python only (optional small LLM call for callout text)
- `trivia_db.py` — `db.fetch / fetchrow / execute` from `services/db.py`
- `telegram.py` — aiogram `Bot` object, configured from `config.py`
- `trivia_bot.py` — composes `trivia_db`, `scoring`, `rivalry`, `telegram`
- `scheduler.py` — composes `question_generator`, `trivia_db`, `telegram`

---

## Data flow

```
APScheduler (9am daily)
  └─ job_post_daily_quiz()
       ├─ question_generator.generate_theme()     → str
       ├─ question_generator.generate_questions() → list[QuizQuestion]
       ├─ trivia_db.create_round()                → Round (Postgres)
       └─ telegram.send_quiz_message()            → message_id (Telegram)

User taps A/B/C/D button
  └─ trivia_bot callback handler
       ├─ trivia_db.record_answer()               → Postgres write
       └─ telegram.acknowledge()                  → ephemeral private reply

APScheduler (every 60s)
  └─ job_close_expired_rounds()
       ├─ trivia_db.get_open_expired_rounds()     → list[Round]
       ├─ scoring.compute_round_elos()            → list[ELOUpdate] (pure Python)
       ├─ trivia_db.save_round_scores()           → Postgres transaction
       ├─ trivia_db.upsert_rivalry()              → Postgres write
       ├─ rivalry.find_notable_rivals()           → list[RivalryCallout]
       └─ telegram.send_results_message()         → Telegram post

User types /leaderboard, /me, /rivalry, /score, /help
  └─ trivia_bot command handler
       ├─ trivia_db.*()                           → Postgres read
       └─ telegram.reply()                        → Telegram reply
```

---

## Database (9 tables, all prefixed `trivia_`)

### Identity
- `trivia_seasons` — competition periods (name, started_at, ended_at, playoff_done)
- `trivia_players` — one row per player (telegram_id PK, elo, streak_current, streak_best, season_id)

### Round lifecycle
- `trivia_rounds` — daily quiz sessions (season_id, theme, status, scheduled_for, closes_at, message_id)
- `trivia_questions` — 5 per round (round_id, position, question_text, A/B/C/D choices, correct_choice, explanation)
- `trivia_answers` — one row per (player, question); UNIQUE (question_id, player_id)

### Scoring & ratings
- `trivia_round_scores` — aggregated result per player per round (correct_count, rank, elo_before, elo_after, elo_delta)
- `trivia_elo_history` — audit log of every ELO change (player_id, round_id, old, new, delta, reason)
- `trivia_rivalries` — pre-aggregated head-to-head (player_a_id < player_b_id always; a_wins, b_wins, ties)
- `trivia_playoffs` — season-end bracket matches (season_id, round_number, player_a/b, winner_id, status)

### Key constraints
- `trivia_answers(question_id, player_id)` UNIQUE — prevents double-answering
- `trivia_rivalries(player_a_id, player_b_id)` UNIQUE — one row per pair
- `trivia_round_scores(round_id, player_id)` UNIQUE — one score row per player per round
- All FK relationships enforced at DB level

---

## Migration files

```
migrations/
  001_trivia_seasons.sql
  002_trivia_players.sql
  003_trivia_rounds.sql
  004_trivia_questions.sql
  005_trivia_answers.sql
  006_trivia_round_scores.sql
  007_trivia_elo_history.sql
  008_trivia_rivalries.sql
  009_trivia_playoffs.sql
  010_trivia_indexes.sql
```

Applied automatically at startup via `db.apply_migrations("migrations/")`.

---

## Build phases

| Phase | What gets built | Done when |
|-------|----------------|-----------|
| 0 | Docs (this file + user_stories, failure_modes, scenarios, policy) | All docs complete |
| 1 | Migrations + trivia_db.py + integration tests | Tables in Neon, tests green |
| 2 | scoring.py + unit tests | ELO tests pass offline |
| 3 | question_generator.py + integration test | 5 well-formed questions generated |
| 4 | Bot shell + /join | `/join` creates a DB row in real group |
| 5 | Round lifecycle (post → collect → score → results) | Full round works end-to-end |
| 6 | Commands + rivalry callouts | All commands return correct output |
| 7 | Seasons + playoffs + Railway deploy | Runs autonomously on Railway |
