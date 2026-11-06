CREATE TABLE labs (id uuid PRIMARY KEY, name text NOT NULL);
CREATE TABLE app_users (
 id uuid PRIMARY KEY, lab_id uuid NOT NULL REFERENCES labs(id),
 role text NOT NULL CHECK (role IN ('user','admin')), enabled boolean NOT NULL DEFAULT true
);
CREATE TABLE access_tokens (
 digest text PRIMARY KEY, user_id uuid NOT NULL REFERENCES app_users(id), expires_at timestamptz NOT NULL
);
CREATE TABLE devices (
 id uuid PRIMARY KEY, lab_id uuid NOT NULL REFERENCES labs(id), name text NOT NULL,
 UNIQUE(id,lab_id)
);
CREATE TABLE material_versions (
 id uuid PRIMARY KEY, lab_id uuid NOT NULL REFERENCES labs(id), device_id uuid,
 owner_id uuid NOT NULL REFERENCES app_users(id), version integer NOT NULL DEFAULT 1,
 storage_key text NOT NULL UNIQUE, sha256 text NOT NULL, media_type text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(device_id,lab_id) REFERENCES devices(id,lab_id)
);
CREATE TABLE async_tasks (
 id uuid PRIMARY KEY, material_id uuid NOT NULL UNIQUE REFERENCES material_versions(id),
 user_id uuid NOT NULL REFERENCES app_users(id), lab_id uuid NOT NULL REFERENCES labs(id),
 operation text NOT NULL DEFAULT 'material.create', idempotency_key text NOT NULL,
 payload_hash text NOT NULL, status text NOT NULL DEFAULT 'queued'
 CHECK(status IN ('queued','processing','ready','failed')),
 stage text NOT NULL DEFAULT 'queued' CHECK(stage IN ('queued','parse','chunk','embed','store')),
 attempts integer NOT NULL DEFAULT 0 CHECK(attempts >= 0),
 retries integer NOT NULL DEFAULT 0 CHECK(retries BETWEEN 0 AND 2),
 error_code text, started_at timestamptz, finished_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(user_id,operation,idempotency_key)
);
CREATE TABLE task_outbox (
 task_id uuid PRIMARY KEY REFERENCES async_tasks(id), created_at timestamptz NOT NULL DEFAULT now(),
 published_at timestamptz
);
CREATE INDEX outbox_pending ON task_outbox(created_at) WHERE published_at IS NULL;
CREATE TABLE task_audit (
 id uuid PRIMARY KEY, actor_id uuid NOT NULL REFERENCES app_users(id),
 task_id uuid NOT NULL REFERENCES async_tasks(id), action text NOT NULL,
 request_id uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
