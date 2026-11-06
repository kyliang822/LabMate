ALTER TABLE app_users ADD COLUMN login_name text UNIQUE;
ALTER TABLE app_users ADD COLUMN password_hash text;
CREATE TABLE auth_signing_keys (
 id integer PRIMARY KEY CHECK(id=1), secret bytea NOT NULL
);
CREATE TABLE login_buckets (
 name_hash text NOT NULL, bucket bigint NOT NULL, attempts integer NOT NULL,
 PRIMARY KEY(name_hash,bucket)
);
CREATE TABLE ai_configs (
 lab_id uuid PRIMARY KEY REFERENCES labs(id), version integer NOT NULL DEFAULT 0,
 assistant_name text NOT NULL DEFAULT 'LabMate',
 prompt_prefix text NOT NULL DEFAULT '以下为授权资料原文片段，请核对出处。',
 result_limit integer NOT NULL DEFAULT 5 CHECK(result_limit BETWEEN 1 AND 20)
);
CREATE TABLE ai_config_commands (
 user_id uuid NOT NULL REFERENCES app_users(id), key text NOT NULL,
 payload_hash text NOT NULL, result jsonb NOT NULL, PRIMARY KEY(user_id,key)
);
CREATE TABLE ai_config_audit (
 id uuid PRIMARY KEY, user_id uuid NOT NULL REFERENCES app_users(id),
 lab_id uuid NOT NULL REFERENCES labs(id), version integer NOT NULL,
 request_id uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE skill_runs (
 id uuid PRIMARY KEY, actor_id uuid NOT NULL REFERENCES app_users(id),
 lab_id uuid NOT NULL REFERENCES labs(id), skill_id text NOT NULL,
 skill_version text NOT NULL, config_version integer NOT NULL,
 status text NOT NULL, duration_ms double precision NOT NULL CHECK(duration_ms>=0),
 usage jsonb NOT NULL, request_id uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX skill_runs_actor ON skill_runs(lab_id,actor_id,created_at DESC);
