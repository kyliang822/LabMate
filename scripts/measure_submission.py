"""20 real curl submissions, immutable raw time_total and nearest-rank P95 evidence."""
import argparse
import json
import subprocess
import uuid
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--identities', type=Path, required=True)
    parser.add_argument('--file', type=Path, required=True)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--output', type=Path, default=Path('reports/evidence/submission-timings.json'))
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Refusing to overwrite timing evidence; choose a new --output path.')
    token = json.loads(args.identities.read_text())['actors']['adminA']['token']
    results = []
    for index in range(20):
        key = str(uuid.uuid4())
        # Credentials travel in stdin curl configuration, not process arguments or printed commands.
        config = 'header = ' + json.dumps('Authorization: Bearer ' + token) + '\n'
        result = subprocess.run(['curl', '--silent', '--show-error', '--config', '-', '--max-time', '30',
                                 '-H', 'Idempotency-Key: ' + key, '-F', 'file=@' + str(args.file.resolve()),
                                 '-w', '\n%{http_code} %{time_total}', args.base_url.rstrip('/') + '/api/v1/materials'],
                                input=config, capture_output=True, text=True)
        if result.returncode:
            results.append({'index': index + 1, 'idempotency_key': key, 'curl_exit': result.returncode})
            continue
        body, metrics = result.stdout.rsplit('\n', 1)
        status, elapsed = metrics.split()
        results.append({'index': index + 1, 'idempotency_key': key, 'status_code': int(status),
                        'time_total': float(elapsed), 'response': json.loads(body)})
    success = [x['time_total'] for x in results if x.get('status_code') == 202]
    evidence = {'measure': 'curl time_total seconds; 20 distinct keys', 'samples': results,
                'p95': sorted(success)[18] if len(success) == 20 else None,
                'processing_time_comparison': 'pending: query finished_at-started_at for these task_ids'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
    print('Timing evidence saved; P95:', evidence['p95'])
    return int(len(success) != 20)


if __name__ == '__main__':
    raise SystemExit(main())
