-- Migration 001: trivia_seasons — competition periods (Season 1, Season 2, etc.)
-- chat_id = 0 means the global solo season (shared across all solo players).
-- Non-zero chat_id means a group-scoped season for that Telegram group.

CREATE TABLE trivia_seasons (
    id           SERIAL PRIMARY KEY,
    chat_id      BIGINT NOT NULL DEFAULT 0,
    name         TEXT NOT NULL,
    started_at   DATE NOT NULL,
    ended_at     DATE,
    playoff_done BOOLEAN NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ended_after_started CHECK (ended_at IS NULL OR ended_at > started_at)
);
