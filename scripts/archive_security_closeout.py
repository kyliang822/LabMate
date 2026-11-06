"""Archive actual unified scan; retain unknown severities and historical red evidence."""
import argparse
import json
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('summary', type=Path)
    args = parser.parse_args()
    args.summary = args.summary.resolve().relative_to(Path.cwd().resolve())
    summary = load(args.summary)
    artifacts = summary['artifacts']
    if not {'secrets', 'pip_audit', 'npm_audit'} <= artifacts.keys():
        raise SystemExit('BLOCKED: unified scan is incomplete.')
    secret, audit, npm = [load(artifacts[k]) for k in ('secrets', 'pip_audit', 'npm_audit')]
    if secret['partial'] or secret['unreviewed_count']:
        raise SystemExit('BLOCKED: secret scan incomplete or requires review; no successful baseline written.')
    if 'dependencies' not in audit or 'vulnerabilities' not in npm.get('metadata', {}):
        raise SystemExit('BLOCKED: audit output missing; network/tool error is not a clean scan.')
    raw = [(d['name'], d['version'], v['id']) for d in audit['dependencies'] for v in d.get('vulns', [])]
    unique = set(raw)
    # Reuse prior primary-source severity only for exactly matching package/version/advisory ID.
    known = {}
    for path in sorted(Path('reports/evidence').glob('python-severity-*.json'), key=lambda p: p.stat().st_mtime):
        for item in load(path).get('advisories', []):
            known[(item['package'], item['version'], item['audit_id'])] = item.get('severity', 'unknown')
    counts = {s: 0 for s in ('critical', 'high', 'moderate', 'low', 'unknown')}
    for key in unique:
        value = known.get(key, 'unknown')
        counts[value if value in counts else 'unknown'] += 1
    report = {
        'source_summary': str(args.summary), 'head': summary['head'],
        'secrets_candidates': secret['candidate_count'], 'secret_partial': secret['partial'],
        'python_raw_count': len(raw), 'python_unique_count': len(unique),
        'python_severity_counts': counts, 'npm': npm['metadata']['vulnerabilities'],
        'severity_note': 'Only reuse previous primary-source classifications for identical IDs; unknown stays unknown.',
    }
    output = args.summary.with_name(args.summary.stem + '-baseline.json')
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    path = Path('reports/security-baseline.md')
    text = path.read_text(encoding='utf-8-sig') if path.exists() else ''
    marker = '<!-- unified-closeout:' + args.summary.name + ' -->'
    if marker not in text:
        text += f'''\n\n{marker}
## 新功能后的统一安全检查

入口：`.\\.venv\\Scripts\\python.exe -m scripts.check_security`；实际记录：{args.summary.as_posix()}。
秘密扫描完整范围候选{secret['candidate_count']}，partial=false。
Python原始{len(raw)}条，去重{len(unique)}条；严重{counts['critical']}、高危{counts['high']}、中危{counts['moderate']}、低危{counts['low']}、未知{counts['unknown']}。未知不算低风险。
前端统计：{json.dumps(report['npm'])}。
细节：{output.as_posix()}及summary关联原始输出。发现导致非零退出保留；本课不自动修复、旧基线保留。尚需真人独立复核。
'''
        path.write_text(text, encoding='utf-8-sig')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
