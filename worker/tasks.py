"""At-least-once consumer, fenced by a session-level PostgreSQL lock."""
import json
import logging
import os
import uuid

import psycopg
from celery import Celery
from celery.exceptions import SoftTimeLimitExceeded

from backend.app.async_tasks.service import connect
from worker.processing import (
    CHUNK_STRATEGY, ProcessingError, embed_chunks, parse_document, read_upload, split_document,
)

logger = logging.getLogger(__name__)
app = Celery('labmate-worker', broker=os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0'))
app.conf.update(
    task_serializer='json', accept_content=['json'], task_ignore_result=True,
    task_acks_late=True, task_reject_on_worker_lost=True, worker_prefetch_multiplier=1,
    worker_cancel_long_running_tasks_on_connection_loss=True,
    task_soft_time_limit=840, task_time_limit=900,
    broker_transport_options={'visibility_timeout': 1200, 'socket_timeout': 10,
                              'socket_connect_timeout': 10},
    task_routes={'labmate.process_material': {'queue': 'materials'}},
)


def acquire(db, task_id):
    return db.execute('SELECT pg_try_advisory_lock(hashtextextended(%s,804)) AS acquired',
                      (str(task_id),)).fetchone()['acquired']


def audit(db, row, action):
    db.execute('''INSERT INTO task_audit(id,actor_id,task_id,action,request_id)
        VALUES (%s,%s,%s,%s,%s)''', (uuid.uuid4(), row['user_id'], row['id'], action, uuid.uuid4()))


def set_stage(db, task_id, stage):
    db.execute('UPDATE async_tasks SET stage=%s WHERE id=%s', (stage, task_id))
    db.commit()


def failed(db, row, stage, exc):
    # If the connection holding our lock is lost, never reconnect and overwrite a new owner.
    db.rollback()
    if exc.transient and row['retries'] < 2:
        delay = 2 ** (row['retries'] + 1)
        db.execute('''UPDATE async_tasks SET status='queued',retries=retries+1,error_code=%s,
            stage=%s,started_at=NULL WHERE id=%s''', (exc.code, stage, row['id']))
        db.execute('''UPDATE task_outbox SET published_at=NULL,
            available_at=now()+(%s * interval '1 second') WHERE task_id=%s''', (delay, row['id']))
        audit(db, row, 'material.retry_scheduled')
    else:
        db.execute('''UPDATE async_tasks SET status='failed',stage=%s,error_code=%s,finished_at=now()
            WHERE id=%s''', (stage, exc.code, row['id']))
        db.execute('''INSERT INTO task_dead_letters(task_id,cycle,stage,error_code) VALUES (%s,%s,%s,%s)
            ON CONFLICT(task_id,cycle) DO NOTHING''', (row['id'], row['cycle'], stage, exc.code))
        audit(db, row, 'material.failed')
    db.commit()


def process_material(task_id):
    try:
        task_id = uuid.UUID(str(task_id))
    except ValueError:
        return 'invalid_task_id'
    with connect() as db:
        if not acquire(db, task_id):
            return 'busy'
        try:
            row = db.execute('''SELECT t.*,v.storage_key,v.sha256,v.media_type,v.version,
                v.material_id AS logical_material_id FROM async_tasks t
                JOIN material_versions v ON v.id=t.material_id WHERE t.id=%s FOR UPDATE OF t''',
                (task_id,)).fetchone()
            if not row:
                return 'not_found'
            db.execute('UPDATE async_tasks SET attempts=attempts+1 WHERE id=%s', (task_id,))
            audit(db, row, 'material.claimed')
            if row['status'] in {'ready', 'failed'}:
                db.commit()
                return row['status']
            if row['status'] == 'processing':
                # Lock acquisition proves the former session owner has gone. Count the lost
                # attempt as a transient failure; poison documents must not crash-loop forever.
                if row['retries'] >= 2:
                    db.commit()
                    failed(db, row, row['stage'], ProcessingError('worker_lost'))
                    return 'failed'
                row['retries'] += 1
                db.execute('UPDATE async_tasks SET retries=%s WHERE id=%s', (row['retries'], task_id))
            if row['status'] == 'queued':
                due = db.execute('SELECT available_at<=now() AS due FROM task_outbox WHERE task_id=%s',
                                 (task_id,)).fetchone()['due']
                if not due:
                    db.commit()
                    return 'deferred'
            db.execute('''UPDATE async_tasks SET status='processing',started_at=now(),finished_at=NULL,
                error_code=NULL,stage='parse' WHERE id=%s''', (task_id,))
            db.commit()
            stage = 'parse'
            try:
                content = read_upload(row['storage_key'], row['sha256'])
                pages = parse_document(content, row['media_type'])
                stage = 'chunk'
                set_stage(db, task_id, stage)
                chunks = split_document(pages)
                stage = 'embed'
                set_stage(db, task_id, stage)
                model, dimensions, vectors = embed_chunks(chunks)
                stage = 'store'
                set_stage(db, task_id, stage)
                # Lock logical material before publishing. Everything below commits together.
                material = db.execute('SELECT * FROM materials WHERE id=%s FOR UPDATE',
                                      (row['logical_material_id'],)).fetchone()
                if material['deleted_at'] is not None:
                    raise ProcessingError('material_deleted')
                db.execute('DELETE FROM material_chunks WHERE version_id=%s', (row['material_id'],))
                with db.cursor() as cursor:
                    cursor.executemany('''INSERT INTO material_chunks
                        (id,version_id,chunk_index,content,location,embedding)
                        VALUES (%s,%s,%s,%s,%s,%s::vector)''', [
                            (uuid.uuid4(), row['material_id'], i, chunk.content, chunk.location,
                             json.dumps(vector)) for i, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))])
                db.execute('''UPDATE material_versions SET ready_at=now(),embedding_model=%s,
                    embedding_dimensions=%s,chunk_strategy=%s WHERE id=%s''',
                    (model, dimensions, CHUNK_STRATEGY, row['material_id']))
                # Version numbers are monotonic; a slow old worker cannot downgrade publication.
                db.execute('''UPDATE materials SET current_version_id=%s WHERE id=%s AND
                    (current_version_id IS NULL OR
                    (SELECT version FROM material_versions WHERE id=current_version_id)<%s)''',
                    (row['material_id'], row['logical_material_id'], row['version']))
                db.execute("UPDATE async_tasks SET status='ready',error_code=NULL,finished_at=now() WHERE id=%s",
                           (task_id,))
                audit(db, row, 'material.ready')
                db.commit()
                logger.info('material_ready task_id=%s chunks=%s', task_id, len(chunks))
                return 'ready'
            except ProcessingError as exc:
                failed(db, row, stage, exc)
            except SoftTimeLimitExceeded:
                failed(db, row, stage, ProcessingError('processing_timeout', transient=True))
            except psycopg.Error:
                # If DB is still usable, persist a bounded retry. Otherwise let late ack/recovery act.
                failed(db, row, stage, ProcessingError('storage_unavailable', transient=True))
            except Exception:
                logger.error('processing_failed task_id=%s stage=%s', task_id, stage)
                failed(db, row, stage, ProcessingError('processing_failed'))
            return 'not_ready'
        finally:
            # Release only on this connection. A lost session releases locks server-side.
            if not db.closed:
                db.rollback()
                db.execute('SELECT pg_advisory_unlock(hashtextextended(%s,804))', (str(task_id),))
                db.commit()


app.task(name='labmate.process_material')(process_material)
