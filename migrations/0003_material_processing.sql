CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE materials (
 id uuid PRIMARY KEY, lab_id uuid NOT NULL REFERENCES labs(id),
 owner_id uuid NOT NULL REFERENCES app_users(id), device_id uuid,
 current_version_id uuid, deleted_at timestamptz,
 FOREIGN KEY(device_id,lab_id) REFERENCES devices(id,lab_id), UNIQUE(id,lab_id)
);
INSERT INTO materials(id,lab_id,owner_id,device_id)
 SELECT id,lab_id,owner_id,device_id FROM material_versions;
ALTER TABLE material_versions ADD COLUMN material_id uuid;
UPDATE material_versions SET material_id=id;
ALTER TABLE material_versions ALTER COLUMN material_id SET NOT NULL;
ALTER TABLE material_versions ADD CONSTRAINT material_lab_fk
 FOREIGN KEY(material_id,lab_id) REFERENCES materials(id,lab_id);
ALTER TABLE material_versions ADD CONSTRAINT material_version_unique UNIQUE(material_id,version);
ALTER TABLE material_versions ADD COLUMN ready_at timestamptz;
ALTER TABLE material_versions ADD COLUMN embedding_model text;
ALTER TABLE material_versions ADD COLUMN embedding_dimensions integer CHECK(embedding_dimensions > 0);
ALTER TABLE material_versions ADD COLUMN chunk_strategy text;
ALTER TABLE material_versions ADD CONSTRAINT version_material_unique UNIQUE(id,material_id);
ALTER TABLE materials ADD CONSTRAINT current_version_fk
 FOREIGN KEY(current_version_id,id) REFERENCES material_versions(id,material_id);
CREATE TABLE material_chunks (
 id uuid PRIMARY KEY, version_id uuid NOT NULL REFERENCES material_versions(id),
 chunk_index integer NOT NULL CHECK(chunk_index >= 0), content text NOT NULL,
 location text NOT NULL, embedding vector NOT NULL,
 UNIQUE(version_id,chunk_index)
);
CREATE VIEW searchable_chunks AS
 SELECT c.*,v.material_id,v.version,v.lab_id,v.device_id,v.embedding_model,
 v.embedding_dimensions,v.chunk_strategy
 FROM material_chunks c JOIN material_versions v ON v.id=c.version_id
 JOIN materials m ON m.id=v.material_id
 WHERE m.current_version_id=v.id AND m.deleted_at IS NULL AND v.ready_at IS NOT NULL;
ALTER TABLE async_tasks ADD COLUMN cycle integer NOT NULL DEFAULT 0 CHECK(cycle >= 0);
ALTER TABLE task_outbox ADD COLUMN available_at timestamptz NOT NULL DEFAULT now();
CREATE TABLE task_dead_letters (
 task_id uuid NOT NULL REFERENCES async_tasks(id), cycle integer NOT NULL,
 stage text NOT NULL, error_code text NOT NULL, failed_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(task_id,cycle)
);
CREATE TABLE task_commands (
 user_id uuid NOT NULL REFERENCES app_users(id), action text NOT NULL,
 idempotency_key text NOT NULL, task_id uuid NOT NULL REFERENCES async_tasks(id),
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(user_id,action,idempotency_key)
);
CREATE INDEX task_scope_created ON async_tasks(lab_id,user_id,created_at DESC);
CREATE INDEX task_recovery ON async_tasks(status,created_at) WHERE status IN ('queued','processing');
