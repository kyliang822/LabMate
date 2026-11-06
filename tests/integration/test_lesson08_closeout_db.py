import hashlib
import secrets
import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app import lesson08_service as s
from backend.app.async_tasks.service import connect, identity, submit
from backend.app.main import app
from worker import tasks


def test_real_login_signature_and_config_permissions(setup):
    tokens, _, _, users = setup
    username = 'fixture-' + uuid.uuid4().hex
    with connect() as db:
        db.execute('INSERT INTO auth_signing_keys VALUES (1,%s) ON CONFLICT DO NOTHING', (secrets.token_bytes(32),))
        db.execute('UPDATE app_users SET login_name=%s,password_hash=%s WHERE id=%s',
                   (username, s.password_hash('test-password'), users[0]))
    try:
        response = s.login(username, 'test-password')
        token = response['access_token']
        assert token.startswith('v1.') and identity(token)['id'] == users[0]
        with pytest.raises(HTTPException) as caught:
            identity(token[:-1] + ('0' if token[-1] != '0' else '1'))
        assert caught.value.status_code == 401
        with TestClient(app) as client:
            before = client.get('/api/v1/ai-config', headers={'Authorization': 'Bearer ' + token}).json()
            denied = client.put('/api/v1/ai-config', headers={'Authorization': 'Bearer ' + tokens[1],
                                'Idempotency-Key': 'denied'}, json=before)
            assert denied.status_code == 403
            headers = {'Authorization': 'Bearer ' + token, 'Idempotency-Key': 'same'}
            one = client.put('/api/v1/ai-config', headers=headers, json=before)
            two = client.put('/api/v1/ai-config', headers=headers, json=before)
            assert one.status_code == two.status_code == 200 and one.json() == two.json()
            assert one.json()['version'] == before['version'] + 1
            changed = {**before, 'prompt_prefix': 'changed'}
            assert client.put('/api/v1/ai-config', headers=headers, json=changed).status_code == 409
        with connect() as db:
            assert db.execute('SELECT count(*) AS n FROM ai_config_audit WHERE user_id=%s', (users[0],)).fetchone()['n'] == 1
    finally:
        with connect() as db:
            db.execute('DELETE FROM login_buckets WHERE name_hash=%s', (hashlib.sha256(username.encode()).hexdigest(),))


def test_search_scopes_and_real_skill_log(setup, monkeypatch):
    _, _, _, users = setup
    with connect() as db:
        a = db.execute('SELECT * FROM app_users WHERE id=%s', (users[0],)).fetchone()
        b = db.execute('SELECT * FROM app_users WHERE id=%s', (users[1],)).fetchone()
    monkeypatch.setattr(tasks, 'embed_chunks', lambda chunks: ('test-only', 2, [[1., 0.] for _ in chunks]))
    task = submit(a, None, str(uuid.uuid4()), b'fictional-search-marker', '.txt', uuid.uuid4())
    assert tasks.process_material(task) == 'ready'
    assert len(s.search(a, 'fictional-search-marker')) == 1
    assert s.search(b, 'fictional-search-marker') == []
    # SQL wildcard characters are literal, not unrestricted search instructions.
    assert s.search(a, '%') == []
    run = s.run_skill(a, 'fictional-search-marker', None, uuid.uuid4())
    assert len(run['citations']) == 1
    log = s.get_run(a, run['run_id'])
    assert log['actor_id'] == a['id'] and log['status'] == 'success'
    assert log['duration_ms'] >= 0 and log['usage']['llm_called'] is False
    assert log['usage']['retrieved_chunks'] == 1
    with pytest.raises(HTTPException) as caught:
        s.get_run(b, run['run_id'])
    assert caught.value.status_code == 404
    with connect() as db:
        db.execute('UPDATE materials SET deleted_at=now() WHERE id=%s', (run['citations'][0]['material_id'],))
    assert s.search(a, 'fictional-search-marker') == []
