"""Course SEC-05/06 baseline. Records findings without upgrading or fixing dependencies."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'reports/evidence'


def run(args, cwd=ROOT):
    env = {**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'}
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          encoding='utf-8', errors='strict', env=env)


def scan_directory(directory, scope):
    result = run([sys.executable, '-m', 'detect_secrets', 'scan', '--all-files', '--no-verify', str(directory)])
    if result.returncode:
        return {'scope': scope, 'error': 'scanner_failed', 'exit_code': result.returncode}
    data = json.loads(result.stdout)
    findings = []
    for name, matches in data['results'].items():
        for match in matches:
            findings.append({
                'scope': scope, 'path': str(Path(name).relative_to(directory)),
                'type': match['type'], 'line': match['line_number'], 'fingerprint': match['hashed_secret'],
            })
    return {'scope': scope, 'findings': findings}


def secrets_scan():
    scopes = []
    history = run(['git', 'rev-list', '--all'])
    if history.returncode != 0 or not history.stdout.strip():
        raise SystemExit('BLOCKED: full Git repository/history required; clone the supplied bundle or remote first.')
    commits = history.stdout.splitlines()
    if run(['git', 'rev-parse', '--is-shallow-repository']).stdout.strip() == 'true':
        scopes.append({'scope': 'complete-git-history', 'missing': True})
    with tempfile.TemporaryDirectory(prefix='labmate-secret-scan-') as temporary:
        root = Path(temporary)
        # Scan every commit's files, not only added lines or current HEAD.
        for commit in commits:
            snapshot = root / commit
            snapshot.mkdir()
            listing = subprocess.run(['git', 'ls-tree', '-rz', commit], cwd=ROOT, capture_output=True, check=True)
            for entry in listing.stdout.split(b'\0'):
                if not entry:
                    continue
                metadata, raw_name = entry.split(b'\t', 1)
                _, kind, blob = metadata.split()
                if kind != b'blob':
                    continue
                relative = Path(raw_name.decode())
                if relative.is_absolute() or '..' in relative.parts:
                    raise ValueError('unsafe repository path')
                destination = snapshot / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                content = subprocess.run(['git', 'cat-file', 'blob', blob.decode()], cwd=ROOT,
                                         capture_output=True, check=True).stdout
                destination.write_bytes(content)
            scopes.append(scan_directory(snapshot, 'git:' + commit))
        working = root / 'working'
        working.mkdir()
        for name in run(['git', 'ls-files', '-co', '--exclude-standard', '-z']).stdout.split('\0'):
            if not name:
                continue
            source = ROOT / name
            if not source.is_file() or source.is_symlink() or name.startswith('reports/evidence/'):
                continue
            destination = working / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
        scopes.append(scan_directory(working, 'working-tree'))
        for scope, directory in [('frontend-build', ROOT / 'web/dist'),
                                 ('runtime-logs', ROOT / 'reports/runtime-logs')]:
            if not directory.is_dir() or not any(p.is_file() for p in directory.rglob('*')):
                scopes.append({'scope': scope, 'missing': True})
            else:
                scopes.append(scan_directory(directory, scope))
    allow_path = ROOT / 'docs/reviews/secret-false-positives.json'
    allowed = json.loads(allow_path.read_text()) if allow_path.exists() else []
    for scope in scopes:
        for item in scope.get('findings', []):
            # Explicit fingerprint+path+type exceptions only; no blanket plugin exclusion.
            item['false_positive_reason'] = next((x['reason'] for x in allowed if
                all(item[k] == x[k] for k in ('path', 'type', 'fingerprint'))), None)
    findings = [f for s in scopes for f in s.get('findings', [])]
    return {'scanner': 'detect-secrets', 'verification': 'offline; no credential validation requests',
            'commit_count': len(commits), 'scopes': scopes,
            'candidate_count': len(findings),
            'unreviewed_count': sum(not f['false_positive_reason'] for f in findings),
            'partial': any(s.get('missing') or s.get('error') for s in scopes),
            'working_exclusion': 'generated reports/evidence; history scan has no path exclusions'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--secrets-only', action='store_true')
    args = parser.parse_args()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    prefix = EVIDENCE / ('security-' + stamp)
    status = {'timestamp_utc': stamp, 'head': run(['git', 'rev-parse', 'HEAD']).stdout.strip(),
              'dirty': bool(run(['git', 'status', '--porcelain']).stdout), 'artifacts': {}}
    secret = secrets_scan()
    path = str(prefix) + '-secrets.json'
    Path(path).write_text(json.dumps(secret, indent=2, ensure_ascii=False), encoding="utf-8")
    status['artifacts']['secrets'] = str(Path(path).relative_to(ROOT))
    code = 1 if secret['unreviewed_count'] else (2 if secret['partial'] else 0)
    if not args.secrets_only:
        path = str(prefix) + '-pip-audit.json'
        result = run([sys.executable, '-m', 'pip_audit', '-r', 'requirements-dev.txt', '--format', 'json', '--output', path])
        Path(str(prefix) + '-pip-audit-status.txt').write_text(f'exit_code={result.returncode}\n' + result.stderr)
        status['artifacts']['pip_audit'] = str(Path(path).relative_to(ROOT))
        status['pip_audit_exit'] = result.returncode
        code = max(code, int(result.returncode != 0))
        npm_path = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
        if not npm_path:
            raise SystemExit('BLOCKED: npm is required; install Node.js first.')
        npm_args = ([os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', 'npm.cmd', 'audit', '--json']
                    if os.name == 'nt' else [npm_path, 'audit', '--json'])
        npm = run(npm_args, cwd=ROOT / 'web')
        path = str(prefix) + '-npm-audit.json'
        Path(path).write_text(npm.stdout or json.dumps({'error': 'no audit output'}))
        status['artifacts']['npm_audit'] = str(Path(path).relative_to(ROOT))
        status['npm_audit_exit'] = npm.returncode
        code = max(code, int(npm.returncode != 0))
    status['exit_code'] = code
    Path(str(prefix) + '-summary.json').write_text(json.dumps(status, indent=2))
    print(json.dumps(status, indent=2))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
