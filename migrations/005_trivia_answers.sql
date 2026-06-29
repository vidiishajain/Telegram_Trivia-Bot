-- Migration 005: trivia_answers — one row per (player, question).
-- UNIQUE (question_id, player_id): prevents double-answering; enables UPSERT for
-- answer changes (players can change their answer before the window closes).

CREATE TABLE trivia_answers (
    id              BIGSERIAL PRIMARY KEY,
    round_id        INTEGER NOT NULL REFERENCES trivia_rounds(id),
    question_id     INTEGER NOT NULL REFERENCES trivia_questions(id),
    player_id       INTEGER NOT NULL REFERENCES trivia_players(id),
    choice          CHAR(1) NOT NULL,
    is_correct      BOOLEAN,
    answered_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    response_time_s INTEGER,
    CONSTRAINT valid_answer_choice CHECK (choice IN ('A', 'B', 'C', 'D')),
    UNIQUE (question_id, player_id)
);
