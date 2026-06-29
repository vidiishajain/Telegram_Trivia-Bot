-- Migration 008: trivia_rivalries — pre-aggregated head-to-head records per player pair.
-- INVARIANT enforced by CHECK: player_a_id < player_b_id always.
-- This guarantees one row per pair (not two mirrored rows), making lookups O(1).
-- Rivalries are naturally scoped per-chat because players have per-chat rows.

CREATE TABLE trivia_rivalries (
    id             SERIAL PRIMARY KEY,
    player_a_id    INTEGER NOT NULL REFERENCES trivia_players(id),
    player_b_id    INTEGER NOT NULL REFERENCES trivia_players(id),
    a_wins         INTEGER NOT NULL DEFAULT 0,
    b_wins         INTEGER NOT NULL DEFAULT 0,
    ties           INTEGER NOT NULL DEFAULT 0,
    last_played_at TIMESTAMPTZ,
    CONSTRAINT player_order CHECK (player_a_id < player_b_id),
    UNIQUE (player_a_id, player_b_id)
);
