-- Retain every user message that contributed to a memory, including
-- messages that caused an existing memory to be updated.
BEGIN;

CREATE UNIQUE INDEX IF NOT EXISTS conversation_memories_conversation_id_id_uq
    ON conversation_memories (conversation_id, id);
CREATE UNIQUE INDEX IF NOT EXISTS messages_conversation_id_id_uq
    ON messages (conversation_id, id);

CREATE TABLE IF NOT EXISTS memory_sources (
    conversation_id uuid NOT NULL,
    memory_id bigint NOT NULL,
    source_message_id bigint NOT NULL,
    created_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT memory_sources_pk PRIMARY KEY (memory_id, source_message_id),
    CONSTRAINT memory_sources_memory_fk
        FOREIGN KEY (conversation_id, memory_id)
        REFERENCES conversation_memories (conversation_id, id) ON DELETE CASCADE,
    CONSTRAINT memory_sources_message_fk
        FOREIGN KEY (conversation_id, source_message_id)
        REFERENCES messages (conversation_id, id) ON DELETE CASCADE
);

INSERT INTO memory_sources (conversation_id, memory_id, source_message_id)
SELECT cm.conversation_id, cm.id, cm.source_message_id
FROM conversation_memories cm
JOIN messages m
  ON m.conversation_id = cm.conversation_id
 AND m.id = cm.source_message_id
WHERE cm.source_message_id IS NOT NULL
ON CONFLICT (memory_id, source_message_id) DO NOTHING;

COMMIT;
