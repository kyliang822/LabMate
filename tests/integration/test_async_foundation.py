"""Requires a real isolated PostgreSQL database. No skip, fake or SQLite fallback."""
import hashlib
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.app.async_tasks.publisher import publish_once
from backend.app.async_tasks.service import connect
from backend.app.main import app
from scripts.migrate import main as migrate


@pytest.fixture
def setup(tmp_path, monkeypatch):
    if not os.environ.get('DATABASE_URL'):
        pytest.fail('DATABASE_URL must point at an isolated PostgreSQL test DB', pytrace=False)
    migrate()
    migrate()
    monkeypatch.setenv('UPLOAD_DIR', str(tmp_path))
    labs = [uuid.uuid4(), uuid.uuid4()]
    users = [uuid.uuid4(), uuid.uuid4()]
    device = uuid.uuid4()
    tokens = [uuid.uuid4().hex, uuid.uuid4().hex]
    with connect() as db:
        for lab in labs:
            db.execute('INSERT INTO labs VALUES (%s,%s)', (lab, 'fictional test'))
        for user, lab, token, role in zip(users, labs, tokens, ['admin', 'user']):
            db.execute('INSERT INTO app_users(id,lab_id,role) VALUES (%s,%s,%s)', (user, lab, role))
            db.execute("INSERT INTO access_tokens VALUES (%s,%s,now()+interval '1 hour')",
                       (hashlib.sha256(token.encode()).hexdigest(), user))
        db.execute('INSERT INTO devices VALUES (%s,%s,%s)', (device, labs[1], 'fictional device'))
    yield tokens, device, tmp_path, users
    with connect() as db:
        db.execute('DELETE FROM skill_runs WHERE actor_id=ANY(%s)', (users,))
        db.execute('DELETE FROM ai_config_audit WHERE user_id=ANY(%s)', (users,))
        db.execute('DELETE FROM ai_config_commands WHERE user_id=ANY(%s)', (users,))
        db.execute('DELETE FROM ai_configs WHERE lab_id=ANY(%s)', (labs,))
        db.execute('DELETE FROM task_commands WHERE user_id=ANY(%s)', (users,))
        db.execute('DELETE FROM task_dead_letters WHERE task_id IN (SELECT id FROM async_tasks WHERE user_id=ANY(%s))', (users,))
        db.execute('UPDATE materials SET current_version_id=NULL WHERE owner_id=ANY(%s)', (users,))
        db.execute('DELETE FROM material_chunks WHERE version_id IN (SELECT id FROM material_versions WHERE owner_id=ANY(%s))', (users,))
        db.execute('DELETE FROM task_audit WHERE actor_id=ANY(%s)', (users,))
        db.execute('DELETE FROM task_outbox WHERE task_id IN (SELECT id FROM async_tasks WHERE user_id=ANY(%s))', (users,))
        db.execute('DELETE FROM async_tasks WHERE user_id=ANY(%s)', (users,))
        db.execute('DELETE FROM material_versions WHERE owner_id=ANY(%s)', (users,))
        db.execute('DELETE FROM materials WHERE owner_id=ANY(%s)', (users,))
        db.execute('DELETE FROM access_tokens WHERE user_id=ANY(%s)', (users,))
        db.execute('DELETE FROM app_users WHERE id=ANY(%s)', (users,))
        db.execute('DELETE FROM devices WHERE id=%s', (device,))
        db.execute('DELETE FROM labs WHERE id=ANY(%s)', (labs,))


def post(token=None, key='same', body=b'demo', device=None):
    headers = {'Idempotency-Key': key}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    with TestClient(app) as client:
        return client.post('/api/v1/materials', headers=headers,
                           files={'file': ('../../demo.txt', body, 'text/plain')},
                           data={'device_id': str(device)} if device else {})


def test_identity_and_scope(setup):
    tokens, device, path, users = setup
    assert post().status_code == 401
    assert post('fake').status_code == 401
    assert post(tokens[1]).status_code == 403
    cross = post(tokens[0], device=device)
    missing = post(tokens[0], device=uuid.uuid4())
    assert cross.status_code == missing.status_code == 404
    assert cross.json()['code'] == missing.json()['code'] == 'not_found'
    with connect() as db:
        assert db.execute('SELECT count(*) AS n FROM async_tasks WHERE user_id=ANY(%s)', (users,)).fetchone()['n'] == 0
    assert list(path.iterdir()) == []


def test_concurrent_submission_and_constraints(setup):
    tokens, _, path, users = setup
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: post(tokens[0]), range(2)))
    assert [r.status_code for r in responses] == [202, 202]
    result = responses[0].json()
    assert set(result) == {'task_id', 'status'}
    assert result == responses[1].json()
    assert post(tokens[0], body=b'changed').status_code == 409
    with connect() as db:
        task = db.execute('SELECT * FROM async_tasks WHERE id=%s', (result['task_id'],)).fetchone()
        assert task['status'] == 'queued' and task['attempts'] == 0 and task['user_id'] == users[0]
        for table in ['task_outbox', 'task_audit']:
            assert db.execute(f'SELECT count(*) AS n FROM {table} WHERE task_id=%s', (task['id'],)).fetchone()['n'] == 1
        # Deliberately bypass API; database uniqueness itself must reject duplicate keys.
        with pytest.raises(psycopg.errors.UniqueViolation) as duplicate:
            with db.transaction():
                new_material = uuid.uuid4()
                db.execute('''INSERT INTO material_versions(id,lab_id,owner_id,storage_key,sha256,media_type,material_id,version)
                    SELECT %s,lab_id,owner_id,%s,sha256,media_type,material_id,version+1 FROM material_versions WHERE id=%s''',
                    (new_material, str(uuid.uuid4()), task['material_id']))
                db.execute('''INSERT INTO async_tasks(id,material_id,user_id,lab_id,idempotency_key,payload_hash)
                    SELECT %s,%s,user_id,lab_id,idempotency_key,payload_hash FROM async_tasks WHERE id=%s''',
                    (uuid.uuid4(), new_material, task['id']))
        assert duplicate.value.diag.constraint_name == 'async_tasks_user_id_operation_idempotency_key_key'
    assert len(list(path.iterdir())) == 1
    assert next(path.iterdir()).read_bytes() == b'demo'


def test_outbox_rollback(setup):
    tokens, _, _, _ = setup
    task = post(tokens[0]).json()['task_id']

    class Offline:
        def send_task(self, *args, **kwargs):
            raise ConnectionError('injected broker failure')

    with pytest.raises(ConnectionError):
        publish_once(Offline())
    with connect() as db:
        assert db.execute('SELECT published_at FROM task_outbox WHERE task_id=%s', (task,)).fetchone()['published_at'] is None
