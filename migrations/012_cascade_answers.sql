-- Migration 012: add ON DELETE CASCADE to trivia_answers.round_id.
-- This lets deleting a round automatically clean up its answers,
-- which is safe because answers are meaningless without their round.

ALTER TABLE trivia_answers
    DROP CONSTRAINT trivia_answers_round_id_fkey,
    ADD CONSTRAINT trivia_answers_round_id_fkey
        FOREIGN KEY (round_id) REFERENCES trivia_rounds(id) ON DELETE CASCADE;
