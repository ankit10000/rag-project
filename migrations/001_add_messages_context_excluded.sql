-- Marks messages that must no longer feed history, summaries or
-- memory extraction (e.g. the source of a deleted memory).
-- Idempotent: safe to run more than once.
ALTER TABLE messages
    ADD COLUMN IF NOT EXISTS context_excluded boolean NOT NULL DEFAULT false;
