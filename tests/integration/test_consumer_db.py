"""Real PostgreSQL/pgvector, fake embedding provider only. Redis evidence is separate."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi import HTTPException

from backend.app.async_tasks import queries
from backend.app.async_tasks.service import connect, submit
from scripts.recover_tasks import recover
from worker import tasks
from worker.processing import ProcessingError



@pytest.fixture
def actor_task(setup):
    _, _, _, users = setup
    with connect() as db:
        actor = db.execute('SELECT * FROM app_users WHERE id=%s', (users[0],)).fetchone()
    task_id = uuid.UUID(submit(actor, None, str(uuid.uuid4()), b'fictional manual', '.txt', uuid.uuid4()))
    return actor, task_id


@pytest.fixture
def fake_embed(monkeypatch):
    monkeypatch.setattr(tasks, 'embed_chunks', lambda chunks: ('test-only', 2, [[1., 0.] for _ in chunks]))


def test_duplicate_success_is_idempotent(actor_task, fake_embed):
    actor, task_id = actor_task
    assert tasks.process_material(task_id) == 'ready'
    assert tasks.process_material(task_id) == 'ready'
    status = queries.task_status(actor, task_id)
    assert status['status'] == 'ready' and status['attempts'] == 2
    with connect() as db:
        rows = db.execute('SELECT * FROM searchable_chunks WHERE version_id=%s', (status['version_id'],)).fetchall()
        assert len(rows) == 1 and rows[0]['content'] == 'fictional manual'
        assert rows[0]['embedding_dimensions'] == 2
        assert db.execute('SELECT count(*) AS n FROM task_audit WHERE task_id=%s AND action=%s',
                          (task_id, 'material.ready')).fetchone()['n'] == 1


def test_scope_and_manual_retry_are_real_db(actor_task, setup, monkeypatch):
    actor, task_id = actor_task
    wrong = {**actor, 'id': setup[3][1]}
    for who in [wrong, {**actor, 'lab_id': uuid.uuid4()}]:
        with pytest.raises(HTTPException) as exc:
            queries.task_status(who, task_id)
        assert exc.value.status_code == 404
    monkeypatch.setattr(tasks, 'embed_chunks', lambda _: (_ for _ in ()).throw(ProcessingError('embedding_not_configured')))
    tasks.process_material(task_id)
    assert queries.task_status(actor, task_id)['status'] == 'failed'
    key = str(uuid.uuid4())
    assert queries.retry_task(actor, task_id, key, uuid.uuid4())['status'] == 'accepted'
    assert queries.retry_task(actor, task_id, key, uuid.uuid4())['status'] == 'accepted'
    status = queries.task_status(actor, task_id)
    assert status['cycle'] == 1 and status['retries'] == 0 and status['status'] == 'queued'
    with connect() as db:
        assert db.execute('SELECT count(*) AS n FROM task_dead_letters WHERE task_id=%s', (task_id,)).fetchone()['n'] == 1
        assert db.execute('SELECT count(*) AS n FROM material_chunks WHERE version_id=%s', (status['version_id'],)).fetchone()['n'] == 0


def test_transient_failure_stops_after_two_retries(actor_task, monkeypatch):
    actor, task_id = actor_task
    monkeypatch.setattr(tasks, 'embed_chunks', lambda _: (_ for _ in ()).throw(ProcessingError('temporary', True)))
    for _ in range(3):
        with connect() as db:
            db.execute("UPDATE task_outbox SET available_at=now()-interval '1 second' WHERE task_id=%s", (task_id,))
        tasks.process_material(task_id)
    status = queries.task_status(actor, task_id)
    assert status['status'] == 'failed' and status['retries'] == 2 and status['attempts'] == 3


def test_concurrent_duplicate_and_recovery_do_not_steal_owner(actor_task, monkeypatch):
    actor, task_id = actor_task
    entered, release = Event(), Event()
    def embed(chunks):
        entered.set()
        assert release.wait(10)
        return 'test-only', 2, [[1., 0.] for _ in chunks]
    monkeypatch.setattr(tasks, 'embed_chunks', embed)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(tasks.process_material, task_id)
        try:
            assert entered.wait(10)
            assert tasks.process_material(task_id) == 'busy'
            with connect() as db:
                db.execute("UPDATE async_tasks SET started_at=now()-interval '2 hours' WHERE id=%s", (task_id,))
            result = recover(1200, apply=True)
            assert {'task_id': str(task_id), 'action': 'active_skipped'} in result
        finally:
            release.set()
        assert future.result() == 'ready'
    assert queries.task_status(actor, task_id)['status'] == 'ready'


def test_old_version_cannot_replace_new(actor_task, fake_embed):
    actor, old = actor_task
    material = queries.task_status(actor, old)['material_id']
    new = submit(actor, None, str(uuid.uuid4()), b'new version', '.txt', uuid.uuid4(), material_id=material)
    assert tasks.process_material(new) == 'ready'
    assert tasks.process_material(old) == 'ready'
    with connect() as db:
        chunks = db.execute('SELECT * FROM searchable_chunks WHERE material_id=%s', (material,)).fetchall()
    assert len(chunks) == 1 and chunks[0]['content'] == 'new version' and chunks[0]['version'] == 2


def test_store_audit_failure_rolls_back_publication(actor_task, fake_embed, monkeypatch):
    actor, task_id = actor_task
    real = tasks.audit
    def fail_ready(db, row, action):
        if action == 'material.ready':
            raise ProcessingError('injected_audit_failure')
        return real(db, row, action)
    monkeypatch.setattr(tasks, 'audit', fail_ready)
    tasks.process_material(task_id)
    status = queries.task_status(actor, task_id)
    with connect() as db:
        assert db.execute('SELECT count(*) AS n FROM material_chunks WHERE version_id=%s', (status['version_id'],)).fetchone()['n'] == 0
        row = db.execute('SELECT ready_at FROM material_versions WHERE id=%s', (status['version_id'],)).fetchone()
    assert row['ready_at'] is None and status['status'] == 'failed'


def test_redelivery_counts_crashed_attempt_and_stops_poison_loop(actor_task, fake_embed):
    actor, task_id = actor_task
    with connect() as db:
        db.execute("UPDATE async_tasks SET status='processing',retries=2,stage='parse' WHERE id=%s", (task_id,))
    assert tasks.process_material(task_id) == 'failed'
    status = queries.task_status(actor, task_id)
    assert status['status'] == 'failed' and status['error_code'] == 'worker_lost'
    assert status['attempts'] == 1 and status['retries'] == 2
