"""Repeatable SEC-01 and partial SEC-02/04 probes; never prints credential values."""
import argparse
import json
import uuid
import urllib.error
import urllib.request
from pathlib import Path


ID = str(uuid.UUID(int=100))
PROTECTED = [
    ('POST', '/api/v1/materials'), ('GET', '/api/v1/materials'),
    ('GET', '/api/v1/tasks'), ('GET', f'/api/v1/tasks/{ID}'),
    ('POST', f'/api/v1/tasks/{ID}/retry'),
    ('GET', f'/api/v1/materials/{ID}/versions/1/original'),
]


def send(base_url, method, path, headers=None, data=None):
    request = urllib.request.Request(base_url.rstrip('/') + path, method=method, headers=headers or {}, data=data)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        response = opener.open(request, timeout=15)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        return response.code, json.loads(response.read())


def probe(base_url, identities=None):
    results = []
    for method, path in PROTECTED:
        status, body = send(base_url, method, path)
        results.append({'check': 'SEC-01', 'identity': 'anonymous', 'method': method, 'path': path,
                        'expected': 401, 'actual': status,
                        'result': 'green' if status == 401 else 'red', 'body': body})
    if identities:
        actors = identities['actors']
        boundary = 'labmate-' + uuid.uuid4().hex
        data = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="fictional.txt"'
                f'\r\nContent-Type: text/plain\r\n\r\nfictional probe\r\n--{boundary}--\r\n').encode()
        status, _ = send(base_url, 'POST', '/api/v1/materials', headers={
            'Authorization': 'Bearer ' + actors['userA1']['token'],
            'Idempotency-Key': 'security-direct-' + str(uuid.uuid4()),
            'Content-Type': 'multipart/form-data; boundary=' + boundary,
        }, data=data)
        results.append({'check': 'SEC-04', 'identity': 'userA1', 'operation': 'direct admin upload',
                        'expected': 403, 'actual': status,
                        'result': 'green' if status == 403 else 'red',
                        'side_effect_verification': 'must additionally inspect DB as documented'})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--identities', type=Path)
    parser.add_argument('--output', type=Path, default=Path('reports/evidence/permission-probe.json'))
    args = parser.parse_args()
    data = json.loads(args.identities.read_text()) if args.identities else None
    results = probe(args.base_url, data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f'{len(results)} HTTP probes recorded; this does not certify untested authorization or DB side effects.')
    return int(any(row['result'] == 'red' for row in results))


if __name__ == '__main__':
    raise SystemExit(main())
