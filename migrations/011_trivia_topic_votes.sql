-- Migration 011: trivia_topic_votes — group topic voting before a round starts.
--
-- When /trivia is called in a group, a round is created with status='voting'.
-- Each registered player taps a topic button; one row per player per round.
-- The bot checks after each vote: if any topic has > 50% of registered players
-- in that chat, it wins immediately and the round moves to status='open'.
-- If no majority by topic_vote_ends_at, the highest-voted topic wins.

CREATE TABLE trivia_topic_votes (
    id        SERIAL PRIMARY KEY,
    round_id  INTEGER NOT NULL REFERENCES trivia_rounds(id) ON DELETE CASCADE,
    player_id INTEGER NOT NULL REFERENCES trivia_players(id),
    topic     TEXT NOT NULL,
    voted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (round_id, player_id)
);

-- Tally votes per topic for a round efficiently
CREATE INDEX idx_trivia_topic_votes_round ON trivia_topic_votes (round_id, topic);
