-- Migration 006: trivia_round_scores — aggregated per-player score for each round.
-- Pre-computed once at scoring time so leaderboard queries don't re-scan trivia_answers.

CREATE TABLE trivia_round_scores (
    id              SERIAL PRIMARY KEY,
    round_id        INTEGER NOT NULL REFERENCES trivia_rounds(id),
    player_id       INTEGER NOT NULL REFERENCES trivia_players(id),
    correct_count   SMALLINT NOT NULL DEFAULT 0,
    total_questions SMALLINT NOT NULL DEFAULT 0,
    rank            SMALLINT,
    elo_before      INTEGER NOT NULL,
    elo_after       INTEGER NOT NULL,
    elo_delta       INTEGER NOT NULL,
    scored_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (round_id, player_id)
);
