-- Migration 004: trivia_questions — 5 questions per round (A/B/C/D choices).
-- ON DELETE CASCADE: deleting a round removes its questions automatically.

CREATE TABLE trivia_questions (
    id            SERIAL PRIMARY KEY,
    round_id      INTEGER NOT NULL REFERENCES trivia_rounds(id) ON DELETE CASCADE,
    position      SMALLINT NOT NULL,
    question_text TEXT NOT NULL,
    choice_a      TEXT NOT NULL,
    choice_b      TEXT NOT NULL,
    choice_c      TEXT NOT NULL,
    choice_d      TEXT NOT NULL,
    correct_choice CHAR(1) NOT NULL,
    explanation   TEXT,
    difficulty    SMALLINT NOT NULL DEFAULT 2,
    CONSTRAINT valid_correct_choice CHECK (correct_choice IN ('A', 'B', 'C', 'D')),
    CONSTRAINT valid_difficulty CHECK (difficulty BETWEEN 1 AND 3),
    UNIQUE (round_id, position)
);
