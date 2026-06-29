-- Migration 003: trivia_rounds — each quiz session.
--
-- mode:
--   'group' — triggered by /trivia in a group chat; topic chosen by vote.
--   'solo'  — triggered by /play in a private DM; no voting, immediate start.
--
-- chat_id: matches the Telegram chat where this round lives.
--   0 = solo round (the chat_id for a solo player equals their telegram_id,
--       but rounds use 0 to signal "global solo pool").
--
-- status lifecycle:
--   group: voting → open → closed → scored (or failed)
--   solo:            open → closed → scored (or failed)
--
-- topic_vote_ends_at: deadline for group voting (NULL for solo rounds).
--   If no topic wins a majority by this time, the highest-voted topic wins.
--
-- theme starts as '' during the voting phase and is set once a topic wins.

CREATE TABLE trivia_rounds (
    id                  SERIAL PRIMARY KEY,
    chat_id             BIGINT NOT NULL DEFAULT 0,
    season_id           INTEGER NOT NULL REFERENCES trivia_seasons(id),
    mode                TEXT NOT NULL DEFAULT 'group',
    theme               TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'voting',
    scheduled_for       TIMESTAMPTZ NOT NULL,
    closes_at           TIMESTAMPTZ NOT NULL,
    topic_vote_ends_at  TIMESTAMPTZ,
    message_id          BIGINT,
    scored_at           TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT valid_mode   CHECK (mode IN ('group', 'solo')),
    CONSTRAINT valid_status CHECK (status IN ('voting', 'open', 'closed', 'scored', 'failed'))
);
