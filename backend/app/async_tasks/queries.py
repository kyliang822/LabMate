"""Authorization and state changes shared by HTTP and recovery commands."""
import uuid

from fastapi import HTTPException

from backend.app.async_tasks.service import connect

PUBLIC_FIELDS = '''id AS task_id,material_id AS version_id,
    (SELECT material_id FROM material_versions WHERE id=async_tasks.material_id) AS material_id,
    status,stage,attempts,retries,cycle,error_code,
    created_at,started_at,finished_at'''


def task_status(actor, task_id):
    with connect() as db:
        row = db.execute(f'''SELECT {PUBLIC_FIELDS} FROM async_tasks
            WHERE id=%s AND user_id=%s AND lab_id=%s''',
            (task_id, actor['id'], actor['lab_id'])).fetchone()
    if not row:
        raise HTTPException(404, 'not_found')
    return row


def list_tasks(actor, limit=30, before=None):
    with connect() as db:
        return db.execute(f'''SELECT {PUBLIC_FIELDS} FROM async_tasks
            WHERE user_id=%s AND lab_id=%s AND (%s::timestamptz IS NULL OR created_at<%s)
            ORDER BY created_at DESC,id DESC LIMIT %s''',
            (actor['id'], actor['lab_id'], before, before, limit)).fetchall()


def retry_task(actor, task_id, key, request_id):
    if actor['role'] != 'admin':
        raise HTTPException(403, 'forbidden')
    with connect() as db:
        db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,805))', (f'{actor["id"]}:{key}',))
        row = db.execute('''SELECT * FROM async_tasks WHERE id=%s AND user_id=%s AND lab_id=%s
            FOR UPDATE''', (task_id, actor['id'], actor['lab_id'])).fetchone()
        if not row:
            raise HTTPException(404, 'not_found')
        old = db.execute('''SELECT task_id FROM task_commands WHERE user_id=%s
            AND action='task.retry' AND idempotency_key=%s''', (actor['id'], key)).fetchone()
        if old:
            if old['task_id'] != task_id:
                raise HTTPException(409, 'idempotency_conflict')
            return {'task_id': task_id, 'status': 'accepted'}
        if row['status'] != 'failed':
            raise HTTPException(409, 'task_not_failed')
        db.execute('''UPDATE async_tasks SET status='queued',stage='queued',retries=0,cycle=cycle+1,
            error_code=NULL,started_at=NULL,finished_at=NULL WHERE id=%s''', (task_id,))
        db.execute('UPDATE task_outbox SET published_at=NULL,available_at=now() WHERE task_id=%s', (task_id,))
        db.execute('''INSERT INTO task_commands(user_id,action,idempotency_key,task_id)
            VALUES (%s,'task.retry',%s,%s)''', (actor['id'], key, task_id))
        db.execute('''INSERT INTO task_audit(id,actor_id,task_id,action,request_id)
            VALUES (%s,%s,%s,'material.manual_retry',%s)''', (uuid.uuid4(), actor['id'], task_id, request_id))
    return {'task_id': task_id, 'status': 'accepted'}


def list_materials(actor, limit=30):
    with connect() as db:
        return db.execute(
            """SELECT m.id AS material_id,m.device_id,v.id AS version_id,v.version,v.ready_at
            FROM materials m JOIN material_versions v ON v.id=m.current_version_id
            WHERE m.lab_id=%s AND m.deleted_at IS NULL AND v.ready_at IS NOT NULL
            ORDER BY v.ready_at DESC,m.id LIMIT %s""", (actor['lab_id'], limit)).fetchall()


def original(actor, material_id, version):
    with connect() as db:
        row = db.execute(
            """SELECT v.storage_key,v.sha256,v.media_type,m.deleted_at,
            m.current_version_id=v.id AS is_current
            FROM materials m JOIN material_versions v ON v.material_id=m.id
            WHERE m.id=%s AND m.lab_id=%s AND v.version=%s AND v.ready_at IS NOT NULL""",
            (material_id, actor['lab_id'], version)).fetchone()
    if not row:
        raise HTTPException(404, 'not_found')
    return row
