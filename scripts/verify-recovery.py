"""Local recovery exercise: create a synthetic private fixture, encrypt, restore, verify."""
import json
import os
from pathlib import Path
import secrets
from backup import ROOT, create_backup
from verify_restore import verify

runtime = Path(os.environ.get('PRODUCTSTAT_RUNTIME_ROOT', Path.home() / '.local/share/productstat'))
key = runtime / 'backup-key'
if not key.exists():
    key.write_text(secrets.token_urlsafe(64), encoding='ascii')
key.chmod(0o600)
os.environ['BACKUP_KEY_FILE'] = str(key)
fixture = ROOT / 'backend' / 'private_media' / 'recovery-fixture.txt'
fixture.parent.mkdir(parents=True, exist_ok=True)
fixture.write_text('Synthetic ProductStat recovery fixture. No personal information.\n', encoding='utf-8')
backup = create_backup()
result = verify(Path(backup['file']))
print(json.dumps({'backup': backup, 'restore': result}, indent=2))
