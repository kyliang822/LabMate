"""Minimal real login, authorized retrieval, configurable skill and durable audit."""
import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from backend.app.async_tasks.service import connect


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32)
    return f'scrypt-v1${salt}${digest.hex()}'


def password_matches(password, encoded):
    try:
        kind, salt, digest = encoded.split('$')
        return kind == 'scrypt-v1' and hmac.compare_digest(password_hash(password, salt), encoded)
    except (ValueError, TypeError):
        return False


DUMMY_PASSWORD_HASH = password_hash('dummy', '0' * 32)


def signature(token, secret):
    return hmac.new(bytes(secret), token.encode(), hashlib.sha256).hexdigest()


def verify_signature_if_present(token):
    if not token.startswith('v1.'):
        return  # Existing short-lived opaque CLI tokens remain compatible.
    try:
        version, payload, supplied = token.split('.')
        with connect() as db:
            key = db.execute('SELECT secret FROM auth_signing_keys WHERE id=1').fetchone()
        if not key or not hmac.compare_digest(signature(version + '.' + payload, key['secret']), supplied):
            raise ValueError
        claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        if claims['exp'] <= time.time():
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise HTTPException(401, 'unauthorized') from None


def login(username, password):
    name_hash = hashlib.sha256(username.encode()).hexdigest()
    bucket = int(time.time()) // 60
    with connect() as db:
        attempt = db.execute('''INSERT INTO login_buckets VALUES (%s,%s,1)
            ON CONFLICT(name_hash,bucket) DO UPDATE SET attempts=login_buckets.attempts+1
            RETURNING attempts''', (name_hash, bucket)).fetchone()['attempts']
        db.execute('DELETE FROM login_buckets WHERE bucket<%s', (bucket - 10,))
    if attempt > 10:
        raise HTTPException(429, 'login_rate_limited')
    with connect() as db:
        actor = db.execute('SELECT * FROM app_users WHERE login_name=%s AND enabled', (username,)).fetchone()
        # Same expensive operation for unknown users, no user-existence error distinction.
        encoded = actor['password_hash'] if actor and actor['password_hash'] else DUMMY_PASSWORD_HASH
        valid = password_matches(password, encoded)
        if not actor or not valid or not actor['password_hash']:
            raise HTTPException(401, 'unauthorized')
        key = db.execute('SELECT secret FROM auth_signing_keys WHERE id=1').fetchone()
        if not key:
            raise HTTPException(503, 'login_not_initialized')
        payload = base64.urlsafe_b64encode(json.dumps({
            'sub': str(actor['id']), 'exp': int(time.time()) + 3600, 'nonce': secrets.token_hex(16),
        }).encode()).decode().rstrip('=')
        unsigned = 'v1.' + payload
        token = unsigned + '.' + signature(unsigned, key['secret'])
        db.execute("INSERT INTO access_tokens VALUES (%s,%s,now()+interval '1 hour')",
                   (hashlib.sha256(token.encode()).hexdigest(), actor['id']))
    return {'access_token': token, 'token_type': 'bearer', 'expires_in': 3600}


def get_config(actor):
    with connect() as db:
        row = db.execute('SELECT * FROM ai_configs WHERE lab_id=%s', (actor['lab_id'],)).fetchone()
    if not row:
        return {'version': 0, 'assistant_name': 'LabMate', 'prompt_prefix': '以下为授权资料原文片段，请核对出处。', 'result_limit': 5}
    return {k: row[k] for k in ('version', 'assistant_name', 'prompt_prefix', 'result_limit')}


def put_config(actor, payload, key, request_id):
    if actor['role'] != 'admin':
        raise HTTPException(403, 'forbidden')
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    with connect() as db:
        # Serialize lab configuration and command idempotency together.
        db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,808))', (str(actor['lab_id']),))
        old = db.execute('SELECT * FROM ai_config_commands WHERE user_id=%s AND key=%s', (actor['id'], key)).fetchone()
        if old:
            if old['payload_hash'] != digest:
                raise HTTPException(409, 'idempotency_conflict')
            return old['result']
        db.execute('INSERT INTO ai_configs(lab_id) VALUES (%s) ON CONFLICT DO NOTHING', (actor['lab_id'],))
        current = db.execute('SELECT version FROM ai_configs WHERE lab_id=%s FOR UPDATE', (actor['lab_id'],)).fetchone()['version']
        if payload['version'] != current:
            raise HTTPException(409, 'configuration_conflict')
        row = db.execute('''UPDATE ai_configs SET assistant_name=%s,prompt_prefix=%s,result_limit=%s,
            version=version+1 WHERE lab_id=%s RETURNING version,assistant_name,prompt_prefix,result_limit''',
            (payload['assistant_name'], payload['prompt_prefix'], payload['result_limit'], actor['lab_id'])).fetchone()
        db.execute('INSERT INTO ai_config_commands VALUES (%s,%s,%s,%s)', (actor['id'], key, digest, Jsonb(row)))
        db.execute('INSERT INTO ai_config_audit(id,user_id,lab_id,version,request_id) VALUES (%s,%s,%s,%s,%s)',
                   (uuid.uuid4(), actor['id'], actor['lab_id'], row['version'], request_id))
    return row


def search(actor, query, device_id=None, limit=5):
    # Literal keyword search; all authorization and readiness conditions precede LIMIT.
    with connect() as db:
        return db.execute('''SELECT id AS chunk_id,material_id,version,version_id,location,content
            FROM searchable_chunks WHERE lab_id=%s
            AND (%s::uuid IS NULL OR device_id=%s OR device_id IS NULL)
            AND strpos(lower(content),lower(%s))>0
            ORDER BY material_id,chunk_index LIMIT %s''',
            (actor['lab_id'], device_id, device_id, query, limit)).fetchall()


def run_skill(actor, query, device_id, request_id):
    started = time.perf_counter()
    config = get_config(actor)
    run_id, status, hits = uuid.uuid4(), 'failed', []
    try:
        hits = search(actor, query, device_id, config['result_limit'])
        status = 'success' if hits else 'no_evidence'
        return {'run_id': run_id, 'skill_id': 'material-guide', 'skill_version': '1.0',
                'assistant_name': config['assistant_name'], 'notice': config['prompt_prefix'],
                'status': status, 'citations': hits,
                'mode': 'authorized_source_excerpts; no LLM generation'}
    finally:
        usage = {'llm_called': False, 'prompt_tokens': 0, 'completion_tokens': 0, 'retrieved_chunks': len(hits)}
        with connect() as db:
            db.execute('''INSERT INTO skill_runs(id,actor_id,lab_id,skill_id,skill_version,
                config_version,status,duration_ms,usage,request_id)
                VALUES (%s,%s,%s,'material-guide','1.0',%s,%s,%s,%s,%s)''',
                (run_id, actor['id'], actor['lab_id'], config['version'], status,
                 (time.perf_counter() - started) * 1000, Jsonb(usage), request_id))


def get_run(actor, run_id):
    with connect() as db:
        row = db.execute('SELECT * FROM skill_runs WHERE id=%s AND actor_id=%s AND lab_id=%s',
                         (run_id, actor['id'], actor['lab_id'])).fetchone()
    if not row:
        raise HTTPException(404, 'not_found')
    return row
