-- Demonstrated need: atomic retry identity and durable answer metadata.
-- Explicit guarded setup only; no automatic startup migration.
BEGIN;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS turn_id uuid;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS answer_metadata jsonb;
CREATE UNIQUE INDEX IF NOT EXISTS messages_v2_turn_role_uq
 ON messages(owner_id,conversation_id,turn_id,role) WHERE turn_id IS NOT NULL;
-- Non-content receipts survive message removal, preventing replay resurrection.
CREATE TABLE IF NOT EXISTS v2_turn_receipts (
 owner_id uuid NOT NULL DEFAULT nullif(current_setting('app.user_id',true),'')::uuid,
 conversation_id uuid NOT NULL, turn_id uuid NOT NULL, question_sha256 text NOT NULL,
 PRIMARY KEY(owner_id,conversation_id,turn_id),
 FOREIGN KEY(owner_id,conversation_id) REFERENCES conversations(owner_id,id) ON DELETE CASCADE
);
ALTER TABLE v2_turn_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE v2_turn_receipts FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='v2_turn_receipts' AND policyname='v2_turn_owner') THEN
  CREATE POLICY v2_turn_owner ON v2_turn_receipts
   USING (owner_id=nullif(current_setting('app.user_id',true),'')::uuid)
   WITH CHECK (owner_id=nullif(current_setting('app.user_id',true),'')::uuid);
 END IF;
END $$;
COMMIT;
