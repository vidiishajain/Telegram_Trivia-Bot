# Scenarios

**Stage 3 — Concrete end-to-end walkthroughs.**

These are the test checklist for stage 8. Each has a real example input and a specific expected output. Run through every one of these before calling the project done.

---

## Happy path — full round lifecycle

**Scenario:** Normal morning quiz, 4 players, all answer, no ties.

1. 9:00am UTC: APScheduler fires `job_post_daily_quiz()`.
2. LLM generates theme: "90s Cartoon Villains."
3. LLM generates 5 questions, e.g.:
   - Q1: "Which villain wanted to skin 101 Dalmatians?" A) Scar B) Cruella de Vil ✓ C) Ursula D) Gaston
4. Bot posts to group:
   ```
   🎮 Daily Quiz — 90s Cartoon Villains
   ⏰ Closes at 11:00am UTC

   Q1. Which villain wanted to skin 101 Dalmatians?
   [A] [B] [C] [D]
   ...
   ```
   Message has 5 inline button rows.
5. Vidisha taps B (correct), Dana taps A (wrong), Alex taps B (correct), Sam taps C (wrong).
6. 11:00am UTC: `job_close_expired_rounds()` detects round past `closes_at`.
7. Scores computed: Vidisha 3/5, Alex 2/5, Sam 2/5, Dana 1/5.
8. ELO computed via pairwise: Vidisha wins most matches, gains +24. Dana loses most, loses −18.
9. Rivalries updated: Vidisha vs Dana head-to-head +1 win for Vidisha.
10. Bot posts results:
    ```
    🏆 Results — 90s Cartoon Villains

    1. Vidisha — 3/5 ▲ +24 ELO (now 1224) 🔥 3-day streak
    2. Alex — 2/5 ▲ +6 ELO (now 1206)
    3. Sam — 2/5 ▼ −4 ELO (now 996)
    4. Dana — 1/5 ▼ −22 ELO (now 978)

    📊 Rivalry spotlight: Vidisha has now beaten Dana 3 rounds in a row. Dana — redemption round?

    Q1 answer: B) Cruella de Vil — she wants a dalmatian coat in the 1961 film.
    ```

**Expected:** All 4 rows in `trivia_answers`, all 4 rows in `trivia_round_scores`, ELO in `trivia_players` updated, `trivia_rivalries` updated, round status = `scored`.

---

## New player joins

**Scenario:** Alex is new to the group, hasn't played before.

1. Alex types `/join` in the group.
2. Bot replies: "Welcome, Alex! You're in 🎉 Your starting ELO is 1200. The next quiz drops tomorrow at 9am UTC. Type /help to see commands."
3. New row in `trivia_players`: `telegram_id=alex_id, display_name="Alex", elo=1200, streak_current=0`.

**Expected:** Row exists in DB. Alex gets no ELO history yet.

---

## Player answers after window closes

**Scenario:** Sam tries to answer Q3 at 11:05am (5 minutes after close).

1. Sam taps the [C] button on Q3.
2. Round status is `scored`. Bot replies privately: "⏰ This round is closed — results are already posted. Tap /score to see the standings."
3. No row written to `trivia_answers`.

**Expected:** DB unchanged. Sam sees a friendly message, not an error.

---

## Only one player answers

**Scenario:** Everyone is busy; only Vidisha answers.

1. Vidisha answers all 5 questions correctly (5/5).
2. Round closes. 1 player in scoring pool.
3. No pairwise matches (C(1,2) = 0). Zero ELO changes.
4. Bot posts:
   ```
   🏆 Results — 90s Cartoon Villains

   1. Vidisha — 5/5 (solo round — no ELO changes, no pairwise opponents)

   🔥 Vidisha's 4-day streak continues!
   ```
5. Vidisha's streak increments; ELO unchanged.

**Expected:** `trivia_round_scores` has 1 row, `elo_delta = 0`. `trivia_elo_history` has no entry for this round.

---

## Two players tie

**Scenario:** Vidisha and Alex both score 4/5. Dana scores 2/5.

1. Pairwise: Vidisha vs Alex → draw (0.5 each). Vidisha vs Dana → win. Alex vs Dana → win.
2. Vidisha and Alex both beat Dana, and drew with each other.
3. ELO: Vidisha ≈ +12, Alex ≈ +12, Dana ≈ −24 (varies by starting ELO).
4. Results message reflects tie at the top:
   ```
   1. Vidisha — 4/5 ▲ +12 ELO
   1. Alex — 4/5 ▲ +12 ELO
   3. Dana — 2/5 ▼ −24 ELO
   ```
5. Head-to-head Vidisha vs Alex: tie recorded.

**Expected:** Both rank 1. Rivalry `ties` field incremented for the Vidisha–Alex pair.

---

## Player forgets to answer (streak breaks)

**Scenario:** Dana answered the last 5 rounds (streak=5) but misses today's round.

1. Round closes. Dana has no rows in `trivia_answers` for this round.
2. Dana gets zero ELO change (absence = no penalty, no gain).
3. Dana's `streak_current` resets to 0 (first miss).
4. Results message notes: "Dana — no answer today (streak of 5 broken)."

**Expected:** `trivia_players.streak_current = 0` for Dana. No entry in `trivia_round_scores` for Dana.

---

## `/me` command

**Scenario:** Vidisha types `/me` after 10 rounds.

Bot replies:
```
📊 Your stats, Vidisha

ELO: 1247 (#1 this season)
Streak: 3 days 🔥
Best streak: 7 days
Accuracy: 68% (34/50 correct)
Rounds played: 10

Head-to-head:
• vs Dana: 7W–2L–1T (dominant)
• vs Alex: 4W–5L–1T (rival)
• vs Sam: 6W–3L–1T
```

**Expected:** All values are accurate against DB state. Rivalry framing ("dominant", "rival") is generated.

---

## Season end and playoff

**Scenario:** 30 days pass, season ends automatically.

1. `job_check_season_end()` detects today ≥ `season.started_at + 30 days`.
2. Bot posts season final leaderboard to group.
3. Soft ELO reset applied: all players pulled 50% toward 1200. Recorded in `trivia_elo_history`.
4. Top 4 players seeded into playoff bracket.
5. Playoff rounds posted over the next 4 days (quarterfinals, semis, final).
6. Champion announced with a message: "🏆 Season 1 champion: Vidisha!"
7. New season automatically begins.

**Expected:** `trivia_seasons.ended_at` set, `trivia_playoffs` rows created, new `trivia_seasons` row with `is_active=true`.

---

## Bot restart mid-round

**Scenario:** Railway redeploys at 10:30am while a round is open (closes at 11am).

1. Bot restarts. `apply_migrations()` runs (idempotent, no changes).
2. Startup check: find any `open` rounds where `closes_at` has passed → none (it's 10:30am).
3. APScheduler re-registers all jobs.
4. At 11am: `job_close_expired_rounds()` fires normally, scores the round.

**Expected:** Round completes as if nothing happened. All answers submitted before restart are in the DB (they were written at submission time, not held in memory).

---

## Done = all scenarios pass

When every scenario here produces the exact expected state in the DB and the expected message in Telegram, the bot is working. Add new scenarios as edge cases are discovered.
