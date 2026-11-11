-- Rollback of 003. Memories, messages and the legacy source_message_id column are untouched.
-- Lost on rollback: link_kind labels and source_role (links themselves are kept).
BEGIN;

ALTER TABLE memory_sources DROP CONSTRAINT IF EXISTS memory_sources_message_fk;
ALTER TABLE memory_sources ADD CONSTRAINT memory_sources_message_fk
    FOREIGN KEY (conversation_id, source_message_id)
    REFERENCES messages (conversation_id, id) ON DELETE CASCADE;

ALTER TABLE memory_sources DROP CONSTRAINT IF EXISTS memory_sources_user_source_ck;
ALTER TABLE memory_sources DROP CONSTRAINT IF EXISTS memory_sources_link_kind_ck;
DROP INDEX IF EXISTS memory_sources_message_idx;
ALTER TABLE memory_sources DROP COLUMN IF EXISTS link_kind;
ALTER TABLE memory_sources DROP COLUMN IF EXISTS source_role;
DROP INDEX IF EXISTS messages_conversation_id_id_role_uq;

COMMIT;
