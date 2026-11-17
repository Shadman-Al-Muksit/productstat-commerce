"""Inspect staged files before publication; never print matched secret contents."""
import re
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
patterns = [re.compile(r'ghp_[A-Za-z0-9]{30,}'), re.compile(r'github_pat_[A-Za-z0-9_]{50,}'),
            re.compile(r'sk-proj-[A-Za-z0-9_-]{30,}'), re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')]
failures = []
for name in filter(None, names):
    path = Path(name)
    if any(part in {'.runtime', 'node_modules', '.next', 'private_media', 'backups', 'test-results', 'playwright-report'} for part in path.parts):
        failures.append((name, 'private/runtime directory staged'))
    if path.name.startswith('.env') and not path.name.endswith('.example'):
        failures.append((name, 'environment secrets file staged'))
    if path.suffix in {'.dump', '.sqlite3', '.gpg', '.pyc'}:
        failures.append((name, 'database, backup, or runtime artifact staged'))
    content = subprocess.check_output(['git', 'show', ':' + name], cwd=root)
    if len(content) > 10 * 1024 * 1024:
        failures.append((name, 'file exceeds 10 MB'))
    text = content.decode('utf-8', errors='ignore')
    if any(pattern.search(text) for pattern in patterns):
        failures.append((name, 'possible secret detected'))
if failures:
    for name, reason in failures:
        print(name + ': ' + reason)
    raise SystemExit(1)
print('Staged source scan passed; no private paths or known credential patterns detected.')
