-- Migration 010: performance indexes for common query patterns.

-- Leaderboard: sort active players by ELO descending within a chat
CREATE INDEX idx_trivia_players_elo ON trivia_players (chat_id, elo DESC) WHERE is_active = TRUE;
CREATE INDEX idx_trivia_players_season ON trivia_players (season_id);
CREATE INDEX idx_trivia_players_telegram ON trivia_players (telegram_id);

-- Round lifecycle: scheduler queries open/voting rounds every 60s
CREATE INDEX idx_trivia_rounds_status_closes ON trivia_rounds (status, closes_at);
CREATE INDEX idx_trivia_rounds_chat_status ON trivia_rounds (chat_id, status);
CREATE INDEX idx_trivia_rounds_scheduled ON trivia_rounds (scheduled_for DESC);
CREATE INDEX idx_trivia_rounds_season ON trivia_rounds (season_id);

-- Answer collection: "has player X answered round Y?" and all answers for a round
CREATE INDEX idx_trivia_answers_round_player ON trivia_answers (round_id, player_id);
CREATE INDEX idx_trivia_answers_player ON trivia_answers (player_id);

-- Scoring: per-player scores for a round and per-round scores for a player
CREATE INDEX idx_trivia_round_scores_player ON trivia_round_scores (player_id);
CREATE INDEX idx_trivia_round_scores_round ON trivia_round_scores (round_id);

-- ELO history: chronological chart per player
CREATE INDEX idx_trivia_elo_history_player ON trivia_elo_history (player_id, created_at DESC);

-- Rivalry lookups: find all rivals for a given player (player_a or player_b)
CREATE INDEX idx_trivia_rivalries_player_a ON trivia_rivalries (player_a_id);
CREATE INDEX idx_trivia_rivalries_player_b ON trivia_rivalries (player_b_id);

