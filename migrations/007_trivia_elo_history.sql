-- Migration 007: trivia_elo_history — audit log of every ELO change.
-- trivia_players.elo is always current; this table is the full history.

CREATE TABLE trivia_elo_history (
    id         BIGSERIAL PRIMARY KEY,
    player_id  INTEGER NOT NULL REFERENCES trivia_players(id),
    round_id   INTEGER REFERENCES trivia_rounds(id),
    elo_before INTEGER NOT NULL,
    elo_after  INTEGER NOT NULL,
    delta      INTEGER NOT NULL,
    reason     TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT valid_elo_reason CHECK (reason IN ('round_score', 'season_reset', 'playoff', 'manual'))
);
