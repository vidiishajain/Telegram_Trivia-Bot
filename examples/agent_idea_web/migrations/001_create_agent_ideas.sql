-- Migration 001: the table behind the "agent idea" web demo.
--
-- Migrations are forward-only and run in filename order, each exactly once
-- (see agent.services.db.apply_migrations). Write plain SQL here.

CREATE TABLE IF NOT EXISTS agent_ideas (
    id          text PRIMARY KEY,           -- a uuid4 hex; unguessable, used in the URL
    domain      text NOT NULL,              -- what the user typed
    status      text NOT NULL DEFAULT 'pending',  -- pending | done | error
    stage       text NOT NULL DEFAULT 'queued',   -- queued | researching | writing | drawing | done
    title       text,
    research    text,
    writeup     text,
    where_to_start text,
    image_prompt   text,
    image_url   text,                        -- durable R2 url of the generated diagram
    error       text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
