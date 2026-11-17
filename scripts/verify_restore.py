"""Restore only to a new isolated database; verify database totals and every private file."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import time
import uuid
import psycopg
from backup import ROOT, digest, snapshot

def verify(backup, keep=False):
    target = 'productstat_restore_' + uuid.uuid4().hex[:12]
    source = os.environ['PGDATABASE']
    if source == target or not target.startswith('productstat_restore_'):
        raise SystemExit('Restore target safety check failed.')
    started = time.monotonic()
    created = False
    passed = False
    with tempfile.TemporaryDirectory(prefix='productstat-restore-') as temp:
        work = Path(temp)
        archive = work / 'backup.tar'
        subprocess.run(['gpg', '--batch', '--yes', '--pinentry-mode', 'loopback', '--passphrase-file', os.environ['BACKUP_KEY_FILE'],
                        '--decrypt', '--output', str(archive), str(backup.resolve())], check=True)
        with tarfile.open(archive) as tar:
            tar.extractall(work / 'data', filter='data')
        data = work / 'data'
        dump = data / 'database.dump'
        manifest = json.loads((data / 'manifest.json').read_text())
        if digest(dump) != manifest['database_sha256']:
            raise SystemExit('Backup database checksum mismatch.')
        media = data / 'private_media'
        actual_files = {str(path.relative_to(media)): digest(path) for path in media.rglob('*') if path.is_file()}
        if actual_files != manifest.get('media_sha256', {}):
            raise SystemExit('Restored private-media checksum mismatch.')
        try:
            subprocess.run(['createdb', target], check=True)
            created = True
            subprocess.run(['pg_restore', '--exit-on-error', '--no-owner', '--no-acl', '--dbname', target, str(dump)], check=True)
            with psycopg.connect(dbname=target) as connection:
                actual = snapshot(connection)
            passed = actual == manifest['database_checks']
            result = {'source': source, 'matches': passed, 'private_files_verified': len(actual_files),
                      'elapsed_seconds': round(time.monotonic() - started, 2),
                      'expected': manifest['database_checks'], 'restored': actual,
                      'backup_sha256': digest(backup), 'isolated_target': target}
            evidence = Path(os.environ.get('RESTORE_EVIDENCE_FILE', ROOT / '.runtime' / 'restore-evidence.json'))
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text(json.dumps(result, indent=2), encoding='utf-8')
            if not passed:
                raise SystemExit('Restore totals differ. Isolated restore database retained for inspection.')
            return result
        finally:
            if created and passed and not keep:
                subprocess.run(['dropdb', target], check=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backup', type=Path)
    parser.add_argument('--keep', action='store_true', help='Retain isolated restored database for inspection.')
    args = parser.parse_args()
    print(json.dumps(verify(args.backup, args.keep), indent=2))

