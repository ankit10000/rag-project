-- Phase 5: deterministic memory provenance hardening.
--   * link_kind     : why a message is linked (origin | update | confirmation | legacy)
--   * source_role   : mirrors messages.role so the database itself can require a USER message
--   * message FK    : (conversation_id, id, role), no cascade, DEFERRABLE INITIALLY DEFERRED:
--                     a message cannot disappear and silently erase the evidence trail, yet a
--                     conversation delete still works (the check runs at commit, after the
--                     cascade removed the memories and their links)
--   * lookup index  : message -> memories
-- Non-destructive: no rows of conversation_memories or messages are touched; existing
-- memory_sources rows are only labelled ('legacy') and given their message's real role.
-- Idempotent. Rollback: 003_memory_sources_provenance_down.sql.
BEGIN;

CREATE UNIQUE INDEX IF NOT EXISTS messages_conversation_id_id_role_uq
    ON messages (conversation_id, id, role);

ALTER TABLE memory_sources
    ADD COLUMN IF NOT EXISTS link_kind text NOT NULL DEFAULT 'origin',
    ADD COLUMN IF NOT EXISTS source_role varchar(20);

-- Label pre-existing links (all of them came from the legacy source_message_id backfill)
-- and record the true role of each source message. Runs only for rows not yet labelled.
UPDATE memory_sources ms
   SET source_role = m.role,
       link_kind   = 'legacy'
  FROM messages m
 WHERE m.conversation_id = ms.conversation_id
   AND m.id = ms.source_message_id
   AND ms.source_role IS NULL;

ALTER TABLE memory_sources ALTER COLUMN source_role SET DEFAULT 'user';
ALTER TABLE memory_sources ALTER COLUMN source_role SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'memory_sources_link_kind_ck') THEN
        ALTER TABLE memory_sources ADD CONSTRAINT memory_sources_link_kind_ck
            CHECK (link_kind IN ('origin', 'update', 'confirmation', 'legacy'));
    END IF;

    -- NOT VALID: legacy rows that point at assistant messages are tolerated and kept
    -- (labelled 'legacy'); every NEW row must be a user message.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'memory_sources_user_source_ck') THEN
        ALTER TABLE memory_sources ADD CONSTRAINT memory_sources_user_source_ck
            CHECK (source_role = 'user') NOT VALID;
    END IF;

    -- Replace the cascading message FK by a role-aware, non-cascading one.
    IF EXISTS (SELECT 1 FROM pg_constraint
                WHERE conname = 'memory_sources_message_fk'
                  AND (confdeltype = 'c' OR NOT condeferrable)) THEN
        ALTER TABLE memory_sources DROP CONSTRAINT memory_sources_message_fk;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'memory_sources_message_fk') THEN
        ALTER TABLE memory_sources ADD CONSTRAINT memory_sources_message_fk
            FOREIGN KEY (conversation_id, source_message_id, source_role)
            REFERENCES messages (conversation_id, id, role)
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS memory_sources_message_idx
    ON memory_sources (conversation_id, source_message_id);

COMMIT;
