"""Publish allowlisted verification summaries, never runtime auth or private files."""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs' / 'evidence'
OUTPUT.mkdir(parents=True, exist_ok=True)


def read(name):
    path = ROOT / '.runtime' / name
    return json.loads(path.read_text()), datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def write(name, content):
    (OUTPUT / name).write_text(json.dumps(content, indent=2) + '\n', encoding='utf-8')


for source, destination in [('restore-evidence.json', 'restore.json'), ('seed-evidence.json', 'seed.json')]:
    data, recorded = read(source)
    write(destination, {'recorded_at': recorded, 'synthetic_data_only': True, 'result': data})

data, recorded = read('async-evidence.json')
allowed = ('status', 'real_worker', 'batches', 'workers', 'sku', 'baseline', 'queued_before_worker',
           'after_first', 'after_repeat', 'worker_restart', 'final', 'stock_movements', 'recorded_at')
write('async-worker.json', {'recorded_at': recorded, 'synthetic_data_only': True,
                          'result': {key: data[key] for key in allowed}})

for source, destination in [('k6-summary.json', 'load.json'), ('k6-summary-before-cache.json', 'load-before-cache.json'),
                            ('k6-summary-before-query-tuning.json', 'load-before-query-tuning.json'),
                            ('k6-summary-after-query-tuning-miss.json', 'load-intermediate-miss.json')]:
    data, recorded = read(source)
    allowed = ('catalog_ms', 'analytics_ms', 'http_reqs', 'http_req_failed', 'checks')
    write(destination, {
        'recorded_at': recorded,
        'environment': 'Ubuntu WSL1 on a shared Windows host; 4 logical processors, 7.90 GiB physical RAM',
        'scope': 'API only, local PostgreSQL 17, gunicorn 4 workers/4 threads for final run; initial run preceded tuning',
        'workload': {'browsing_users': 20, 'staff_users': 5, 'think_time_seconds': 1,
                     'independent_authenticated_identities': 25 if destination in {'load.json', 'load-intermediate-miss.json'} else 2,
                     'fixture_skus': 2000, 'fixture_historical_orders': 25000, 'fixture_historical_lines': 75000},
        'report_cache_seconds': 0 if destination == 'load-before-cache.json' else 30,
        'test_state': data.get('state'),
        'metrics': {key: data['metrics'][key] for key in allowed},
        'limitations': 'Short local read workload, with cold requests retained; not a production capacity guarantee or an end-to-end browser load test.',
    })

print('Published allowlisted synthetic verification summaries to docs/evidence.')

npm, npm_date = read('npm-audit.json')
python_audit, python_date = read('python-audit.json')
python_findings = sum(len(package.get('vulns', [])) for package in python_audit.get('dependencies', []))
write('security.json', {'npm_recorded_at': npm_date, 'python_recorded_at': python_date,
                        'npm_production_vulnerabilities': npm['metadata']['vulnerabilities'],
                        'python_reported_vulnerabilities': python_findings,
                        'python_audit_tool': 'pip-audit 2.10.1',
                        'scope': 'Public package advisory checks at the recorded times; not a penetration test or a guarantee against unknown vulnerabilities.'})
