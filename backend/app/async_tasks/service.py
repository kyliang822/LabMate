import hashlib
import os
import uuid
from pathlib import Path

import psycopg
from fastapi import HTTPException
from psycopg.rows import dict_row


def connect():
    return psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row, connect_timeout=5)


def identity(token):
    with connect() as db:
        actor = db.execute('''SELECT u.* FROM access_tokens t JOIN app_users u ON u.id=t.user_id
            WHERE t.digest=%s AND t.expires_at>now() AND u.enabled''',
            (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    if not actor:
        raise HTTPException(401, 'unauthorized')
    return actor


def validate_file(filename, content):
    ext = Path(filename or '').suffix.lower()
    if ext not in {'.txt', '.md', '.pdf'} or not content:
        raise HTTPException(422, 'unsupported_or_empty_file')
    if ext == '.pdf':
        if not content.startswith(b'%PDF-'):
            raise HTTPException(422, 'invalid_pdf_header')
    else:
        try:
            content.decode('utf-8')
        except UnicodeDecodeError:
            raise HTTPException(422, 'invalid_utf8') from None
        if b'\x00' in content:
            raise HTTPException(422, 'invalid_text')
    return ext


def submit(actor, device_id, key, content, ext, request_id):
    checksum = hashlib.sha256(content).hexdigest()
    payload = hashlib.sha256(f'{device_id}:{ext}:{checksum}'.encode()).hexdigest()
    storage = None
    try:
        with connect() as db:
            # Serialize same principal/key across requests; DB uniqueness remains the backstop.
            db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (f'{actor["id"]}:{key}',))
            if device_id and not db.execute('SELECT id FROM devices WHERE id=%s AND lab_id=%s',
                                          (device_id, actor['lab_id'])).fetchone():
                raise HTTPException(404, 'not_found')
            old = db.execute('SELECT id,payload_hash FROM async_tasks WHERE user_id=%s AND operation=%s AND idempotency_key=%s',
                             (actor['id'], 'material.create', key)).fetchone()
            if old:
                if old['payload_hash'] != payload:
                    raise HTTPException(409, 'idempotency_conflict')
                return str(old['id'])
            task_id, material_id = uuid.uuid4(), uuid.uuid4()
            directory = Path(os.environ.get('UPLOAD_DIR', 'uploads'))
            directory.mkdir(parents=True, exist_ok=True)
            storage_key = f'{uuid.uuid4()}{ext}'
            storage = directory / storage_key
            with storage.open('xb') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            db.execute('''INSERT INTO material_versions
                (id,lab_id,device_id,owner_id,storage_key,sha256,media_type) VALUES (%s,%s,%s,%s,%s,%s,%s)''',
                (material_id, actor['lab_id'], device_id, actor['id'], storage_key, checksum, ext[1:]))
            db.execute('''INSERT INTO async_tasks
                (id,material_id,user_id,lab_id,idempotency_key,payload_hash) VALUES (%s,%s,%s,%s,%s,%s)''',
                (task_id, material_id, actor['id'], actor['lab_id'], key, payload))
            db.execute('INSERT INTO task_outbox(task_id) VALUES (%s)', (task_id,))
            db.execute('INSERT INTO task_audit(id,actor_id,task_id,action,request_id) VALUES (%s,%s,%s,%s,%s)',
                       (uuid.uuid4(), actor['id'], task_id, 'material.queued', request_id))
        return str(task_id)
    except BaseException:
        if storage:
            storage.unlink(missing_ok=True)
        raise
