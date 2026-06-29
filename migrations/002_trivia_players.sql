-- Migration 002: trivia_players — one row per (human, context).
--
-- telegram_id: stable Telegram user ID.
-- chat_id: the group chat this player belongs to.
--          0 = solo/global — this player is on the shared solo leaderboard.
--          non-zero = group player scoped to that specific group chat.
--
-- Why a serial PK instead of telegram_id?
-- The same person can exist twice: once as a solo player (chat_id=0)
-- and once per group they play in. Internal FKs reference id (serial).

CREATE TABLE trivia_players (
    id             SERIAL PRIMARY KEY,
    telegram_id    BIGINT NOT NULL,
    chat_id        BIGINT NOT NULL DEFAULT 0,
    username       TEXT,
    display_name   TEXT NOT NULL,
    elo            INTEGER NOT NULL DEFAULT 1200,
    streak_current INTEGER NOT NULL DEFAULT 0,
    streak_best    INTEGER NOT NULL DEFAULT 0,
    total_rounds   INTEGER NOT NULL DEFAULT 0,
    total_correct  INTEGER NOT NULL DEFAULT 0,
    season_id      INTEGER REFERENCES trivia_seasons(id),
    joined_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (telegram_id, chat_id)
);
