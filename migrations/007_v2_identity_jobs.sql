-- v2 additive ownership: existing rows remain unassigned, never auto-adopted.
-- Apply only with the guarded v2 scratch/setup command, never automatically at startup.
BEGIN;
CREATE TABLE IF NOT EXISTS users (
 id uuid PRIMARY KEY, email text UNIQUE NOT NULL, password_hash text NOT NULL,
 display_name text NOT NULL DEFAULT '', role text NOT NULL DEFAULT 'user' CHECK(role IN ('admin','user')),
 status text NOT NULL DEFAULT 'active' CHECK(status IN ('active','disabled')),
 created_at timestamptz NOT NULL DEFAULT now(), password_changed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS user_sessions (
 id uuid PRIMARY KEY, user_id uuid NOT NULL REFERENCES users(id), token_hash text UNIQUE NOT NULL,
 csrf_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL, revoked_at timestamptz
);
CREATE INDEX IF NOT EXISTS user_sessions_user_idx ON user_sessions(user_id);
CREATE TABLE IF NOT EXISTS auth_login_attempts (
 key_hash text PRIMARY KEY, failures integer NOT NULL, window_started_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
 id bigserial PRIMARY KEY, actor_user_id uuid REFERENCES users(id), target_user_id uuid REFERENCES users(id),
 action text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), metadata jsonb NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS documents (
 id uuid PRIMARY KEY, owner_id uuid NOT NULL DEFAULT nullif(current_setting('app.user_id',true),'')::uuid REFERENCES users(id),
 filename text NOT NULL, storage_path text NOT NULL, status text NOT NULL DEFAULT 'queued'
 CHECK(status IN ('queued','running','ready','failed','cancelled','deleted')),
 version bigint NOT NULL DEFAULT 1, pages integer NOT NULL DEFAULT 0, chunks integer NOT NULL DEFAULT 0,
 page_metadata jsonb NOT NULL DEFAULT '[]', created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(owner_id,id)
);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding_model text;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding_dim integer;
CREATE TABLE IF NOT EXISTS jobs (
 id uuid PRIMARY KEY, owner_id uuid NOT NULL DEFAULT nullif(current_setting('app.user_id',true),'')::uuid REFERENCES users(id),
 document_id uuid NOT NULL, document_version bigint NOT NULL, type text NOT NULL DEFAULT 'ingest',
 status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','succeeded','failed','cancelled')),
 attempts integer NOT NULL DEFAULT 0, max_attempts integer NOT NULL DEFAULT 3 CHECK(max_attempts BETWEEN 1 AND 5),
 idempotency_key text NOT NULL, worker_id text, lease_token uuid, lease_until timestamptz,
 heartbeat_at timestamptz, available_at timestamptz NOT NULL DEFAULT now(),
 progress integer NOT NULL DEFAULT 0 CHECK(progress BETWEEN 0 AND 100), error_code text,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(owner_id,idempotency_key), UNIQUE(owner_id,id),
 FOREIGN KEY(owner_id,document_id) REFERENCES documents(owner_id,id)
);
CREATE INDEX IF NOT EXISTS jobs_claim_idx ON jobs(owner_id,status,available_at,created_at);
CREATE TABLE IF NOT EXISTS job_events (
 id bigserial PRIMARY KEY, owner_id uuid NOT NULL DEFAULT nullif(current_setting('app.user_id',true),'')::uuid,
 job_id uuid NOT NULL, event text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(owner_id,job_id) REFERENCES jobs(owner_id,id)
);
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS owner_id uuid DEFAULT nullif(current_setting('app.user_id',true),'')::uuid REFERENCES users(id);
ALTER TABLE messages ADD COLUMN IF NOT EXISTS owner_id uuid DEFAULT nullif(current_setting('app.user_id',true),'')::uuid REFERENCES users(id);
ALTER TABLE conversation_memories ADD COLUMN IF NOT EXISTS owner_id uuid DEFAULT nullif(current_setting('app.user_id',true),'')::uuid REFERENCES users(id);
ALTER TABLE memory_sources ADD COLUMN IF NOT EXISTS owner_id uuid DEFAULT nullif(current_setting('app.user_id',true),'')::uuid REFERENCES users(id);
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS owner_id uuid DEFAULT nullif(current_setting('app.user_id',true),'')::uuid REFERENCES users(id);
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS document_id uuid;
CREATE UNIQUE INDEX IF NOT EXISTS conversations_owner_id_uq ON conversations(owner_id,id);
CREATE UNIQUE INDEX IF NOT EXISTS messages_owner_id_uq ON messages(owner_id,id);
CREATE UNIQUE INDEX IF NOT EXISTS memories_owner_id_uq ON conversation_memories(owner_id,id);
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conname='v2_messages_owner_fk') THEN
 ALTER TABLE messages ADD CONSTRAINT v2_messages_owner_fk FOREIGN KEY(owner_id,conversation_id) REFERENCES conversations(owner_id,id) ON DELETE CASCADE;
 ALTER TABLE conversation_memories ADD CONSTRAINT v2_memories_owner_fk FOREIGN KEY(owner_id,conversation_id) REFERENCES conversations(owner_id,id) ON DELETE CASCADE;
 ALTER TABLE conversation_memories ADD CONSTRAINT v2_memory_source_owner_fk FOREIGN KEY(owner_id,source_message_id) REFERENCES messages(owner_id,id) DEFERRABLE INITIALLY DEFERRED;
 ALTER TABLE memory_sources ADD CONSTRAINT v2_links_conversation_owner_fk FOREIGN KEY(owner_id,conversation_id) REFERENCES conversations(owner_id,id) ON DELETE CASCADE;
 ALTER TABLE memory_sources ADD CONSTRAINT v2_links_memory_owner_fk FOREIGN KEY(owner_id,memory_id) REFERENCES conversation_memories(owner_id,id) ON DELETE CASCADE;
 ALTER TABLE memory_sources ADD CONSTRAINT v2_links_source_owner_fk FOREIGN KEY(owner_id,source_message_id) REFERENCES messages(owner_id,id) DEFERRABLE INITIALLY DEFERRED;
 ALTER TABLE document_chunks ADD CONSTRAINT v2_chunks_document_owner_fk FOREIGN KEY(owner_id,document_id) REFERENCES documents(owner_id,id);
 END IF;
END $$;
CREATE OR REPLACE FUNCTION v2_chunk_document() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.owner_id IS NOT NULL THEN
  SELECT id INTO NEW.document_id FROM documents WHERE owner_id=NEW.owner_id AND id::text=NEW.document_name AND status <> 'deleted';
  IF NEW.document_id IS NULL THEN RAISE EXCEPTION 'owned document unavailable'; END IF;
 END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS v2_chunk_document_trigger ON document_chunks;
CREATE TRIGGER v2_chunk_document_trigger BEFORE INSERT OR UPDATE ON document_chunks FOR EACH ROW EXECUTE FUNCTION v2_chunk_document();
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['documents','jobs','job_events','conversations','messages','conversation_memories','memory_sources','document_chunks'] LOOP
  EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('DROP POLICY IF EXISTS v2_owner ON %I',t);
  EXECUTE format('CREATE POLICY v2_owner ON %I USING (owner_id=nullif(current_setting(''app.user_id'',true),'''')::uuid OR (owner_id IS NULL AND current_setting(''app.tenant_mode'',true)=''legacy'')) WITH CHECK (owner_id=nullif(current_setting(''app.user_id'',true),'''')::uuid OR (owner_id IS NULL AND current_setting(''app.tenant_mode'',true)=''legacy''))',t);
  EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I(owner_id)',t || '_v2_owner_idx',t);
 END LOOP;
END $$;
COMMIT;
