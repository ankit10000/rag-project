-- Roll back attribution while preserving the legacy source_message_id column.
BEGIN;
DROP TABLE IF EXISTS memory_sources;
DROP INDEX IF EXISTS conversation_memories_conversation_id_id_uq;
DROP INDEX IF EXISTS messages_conversation_id_id_uq;
COMMIT;
