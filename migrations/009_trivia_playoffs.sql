-- Migration 009: trivia_playoffs — season-end bracket structure.
-- round_number: 1=quarterfinals, 2=semifinals, 3=final.

CREATE TABLE trivia_playoffs (
    id           SERIAL PRIMARY KEY,
    season_id    INTEGER NOT NULL REFERENCES trivia_seasons(id),
    round_number SMALLINT NOT NULL,
    player_a_id  INTEGER NOT NULL REFERENCES trivia_players(id),
    player_b_id  INTEGER NOT NULL REFERENCES trivia_players(id),
    winner_id    INTEGER REFERENCES trivia_players(id),
    round_id     INTEGER REFERENCES trivia_rounds(id),
    status       TEXT NOT NULL DEFAULT 'pending',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT valid_playoff_status CHECK (status IN ('pending', 'open', 'completed'))
);
