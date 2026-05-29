-- Migration 002: store the research sources (Perplexity citations) as JSON.
--
-- Note the pattern: migrations are FORWARD-ONLY. We don't edit 001; we add 002.
-- Use IF NOT EXISTS so the file is safe even if a column already exists.

ALTER TABLE agent_ideas ADD COLUMN IF NOT EXISTS sources jsonb;
