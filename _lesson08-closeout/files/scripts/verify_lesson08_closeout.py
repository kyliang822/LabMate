"""Real HTTP acceptance: login, SEC-02 retrieval, SEC-03 config and SEC-07 skill logs."""
import argparse
import hashlib
import json
import time
import uuid
from pathlib import Path

from backend.app.async_tasks.service import connect
from scripts.permission_probe import send


def verify(base, credentials):
    tokens, results = {}, []
    def check(name, passed, actual):
        results.append({'check': name, 'result': 'green' if passed else 'red', 'actual': actual})
    def call(name, method, path, body=None, key=None):
        headers = {'Authorization': 'Bearer ' + tokens[name]}
        if key:
            headers['Idempotency-Key'] = key
        if body is not None:
            headers['Content-Type'] = 'application/json'
        return send(base, method, '/api/v1' + path, headers, json.dumps(body).encode() if body is not None else None)
    for name, identity in credentials['actors'].items():
        status, body = send(base, 'POST', '/api/v1/auth/login', {'Content-Type': 'application/json'}, json.dumps(identity).encode())
        check('login-' + name, status == 200 and bool(body.get('access_token')), {'http_status': status})
        if status != 200:
            return results
        tokens[name] = body['access_token']
    status, _ = send(base, 'POST', '/api/v1/auth/login', {'Content-Type': 'application/json'},
                     json.dumps({'username': 'userA1', 'password': 'wrong-test-password'}).encode())
    check('login-wrong-password', status == 401, {'http_status': status})
    # No raw passwords, tokens, document content or full prompt in evidence.
    query = 'scope' + uuid.uuid4().hex
    boundary = 'labmate-' + uuid.uuid4().hex
    data = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="isolation.txt"\r\n'
            f'Content-Type: text/plain\r\n\r\nFictional device evidence {query}\r\n--{boundary}--\r\n').encode()
    status, body = send(base, 'POST', '/api/v1/materials', {
        'Authorization': 'Bearer ' + tokens['adminA'], 'Idempotency-Key': str(uuid.uuid4()),
        'Content-Type': 'multipart/form-data; boundary=' + boundary}, data)
    check('upload-202', status == 202, {'http_status': status})
    if status != 202:
        return results
    task_id = body['task_id']
    for _ in range(60):
        _, task = call('adminA', 'GET', '/tasks/' + task_id)
        if task.get('status') in ('ready', 'failed'):
            break
        time.sleep(1)
    check('upload-ready', task.get('status') == 'ready', {'task_id': task_id, 'status': task.get('status'), 'error_code': task.get('error_code')})
    if task.get('status') != 'ready':
        return results
    for name in ('userA1', 'userB1', 'adminB'):
        status, body = call(name, 'GET', '/search?q=' + query)
        hits = body.get('items', [])
        valid = status == 200 and (len(hits) == 1 if name == 'userA1' else len(hits) == 0)
        if name == 'userA1':
            valid = valid and str(hits[0]['material_id']) == task['material_id']
        check('SEC-02-search-' + name, valid, {'http_status': status, 'result_count': len(hits)})
    _, config = call('adminA', 'GET', '/ai-config')
    with connect() as db:
        baseline_count = db.execute('SELECT count(*) AS n FROM ai_config_audit').fetchone()['n']
    for name in ('userA1', 'userB1'):
        status, _ = call(name, 'PUT', '/ai-config', config, str(uuid.uuid4()))
        check('SEC-03-' + name, status == 403, {'http_status': status})
    _, unchanged = call('adminA', 'GET', '/ai-config')
    with connect() as db:
        current_count = db.execute('SELECT count(*) AS n FROM ai_config_audit').fetchone()['n']
    check('SEC-03-no-side-effect', config == unchanged and baseline_count == current_count,
          {'config_unchanged': config == unchanged, 'audit_delta': current_count - baseline_count})
    # Admin writes the real settings back, validating optimistic version + command idempotency.
    key = str(uuid.uuid4())
    s1, c1 = call('adminA', 'PUT', '/ai-config', config, key)
    s2, c2 = call('adminA', 'PUT', '/ai-config', config, key)
    check('config-admin-idempotent', s1 == s2 == 200 and c1 == c2 and c1.get('version') == config['version'] + 1,
          {'statuses': [s1, s2], 'old_version': config['version'], 'new_version': c1.get('version')})
    status, skill = call('userA1', 'POST', '/skills/material-guide', {'query': query})
    check('SEC-07-skill-call', status == 200 and len(skill.get('citations', [])) == 1,
          {'http_status': status, 'skill_id': skill.get('skill_id'), 'status': skill.get('status')})
    if status == 200:
        status, log = call('userA1', 'GET', '/skill-runs/' + skill['run_id'])
        required = {'actor_id', 'skill_id', 'status', 'duration_ms', 'usage', 'request_id', 'config_version'}
        check('SEC-07-log', status == 200 and required <= log.keys() and log['duration_ms'] >= 0,
              log)  # This endpoint contains metadata only; no credentials or query text.
        status, _ = call('userB1', 'GET', '/skill-runs/' + skill['run_id'])
        check('SEC-07-log-isolation', status == 404, {'http_status': status})
    status, denied_skill = call('userB1', 'POST', '/skills/material-guide', {'query': query})
    check('SEC-02-skill-context-isolation', status == 200 and denied_skill.get('citations') == [],
          {'http_status': status, 'result_count': len(denied_skill.get('citations', []))})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--credentials', default='/tmp/lesson08-login.json')
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--output', default='/tmp/lesson08-closeout-results.json')
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise SystemExit('Evidence exists; choose a new --output rather than overwrite.')
    try:
        results = verify(args.base_url, json.loads(Path(args.credentials).read_text(encoding='utf-8')))
        green = bool(results) and len(results) >= 18 and all(r['result'] == 'green' for r in results)
        report = {'results': results, 'all_checks_green': green,
                  'note': 'Live HTTP/DB evidence; skill is source retrieval, no LLM generation. Peer signature remains human.',
                  'source_sha256': hashlib.sha256(Path('backend/app/lesson08_service.py').read_bytes()).hexdigest()}
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        raise SystemExit(0 if green else 1)
    except (OSError, ValueError) as exc:
        raise SystemExit('BLOCKED: missing/unreadable credentials or response: ' + type(exc).__name__) from None


if __name__ == '__main__':
    main()
