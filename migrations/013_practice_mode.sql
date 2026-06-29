-- Allow practice rounds (fun play, no ELO impact) alongside 'group' and 'solo'
ALTER TABLE trivia_rounds DROP CONSTRAINT IF EXISTS valid_mode;
ALTER TABLE trivia_rounds ADD CONSTRAINT valid_mode
    CHECK (mode IN ('group', 'solo', 'practice'));
