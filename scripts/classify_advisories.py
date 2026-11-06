"""Attach primary-source severity to pip-audit IDs; unknown severity stays unknown."""
import argparse
import json
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def classify(item):
    package, version, vuln = item
    result = {'package': package, 'version': version, 'audit_id': vuln['id'],
              'fixed_versions': vuln.get('fix_versions', []), 'severity': 'unknown'}
    aliases = [vuln['id'], *vuln.get('aliases', [])]
    advisory = next((x for x in aliases if x.startswith('GHSA-')), None)
    if not advisory:
        return result
    url = 'https://api.github.com/advisories/' + advisory
    result['source'] = url
    try:
        request = urllib.request.Request(url, headers={'Accept': 'application/vnd.github+json',
                                                     'User-Agent': 'LabMate-course-baseline'})
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.load(response)
        severity = data.get('severity', 'unknown')
        result.update(severity='moderate' if severity == 'medium' else severity, cvss=data.get('cvss'),
                      html_url=data.get('html_url'), ghsa_id=advisory)
    except (urllib.error.URLError, ValueError, TimeoutError):
        result['lookup'] = 'unavailable; do not count as zero'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audit', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    data = json.loads(args.audit.read_text())
    raw = [(d['name'], d['version'], v) for d in data['dependencies'] for v in d.get('vulns', [])]
    items = list({(name, version, v['id']): (name, version, v) for name, version, v in raw}.values())
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(classify, items))
    counts = {s: sum(r['severity'] == s for r in results) for s in ['critical', 'high', 'moderate', 'low', 'unknown']}
    args.output.write_text(json.dumps({'raw_record_count': len(raw), 'unique_advisory_count': len(results), 'counts': counts, 'advisories': results}, indent=2))
    print(counts)


if __name__ == '__main__':
    main()
