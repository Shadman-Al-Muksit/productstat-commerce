"""Consistent encrypted PostgreSQL/media backup; usable locally or in the backup container."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import psycopg

ROOT = Path(__file__).resolve().parents[1]
CHECKS = {
    'orders': 'SELECT COUNT(*), COALESCE(SUM(grand_total),0) FROM commerce_order',
    'lines': 'SELECT COUNT(*),COALESCE(SUM(quantity),0),COALESCE(SUM(delivered_quantity),0),COALESCE(SUM(returned_quantity),0) FROM commerce_orderline',
    'inventory': 'SELECT COUNT(*),COALESCE(SUM(on_hand),0),COALESCE(SUM(reserved),0) FROM commerce_sku',
    'payments': 'SELECT COUNT(*),COALESCE(SUM(amount),0),COALESCE(SUM(settled_amount),0) FROM commerce_payment',
    'refunds': 'SELECT COUNT(*),COALESCE(SUM(amount),0) FROM commerce_refund',
    'settlements': 'SELECT COUNT(*),COALESCE(SUM(amount),0) FROM commerce_paymentsettlement',
    'order_revisions': 'SELECT COUNT(*) FILTER (WHERE is_current),COUNT(*) FILTER (WHERE NOT is_current),COUNT(supersedes_id) FROM commerce_order',
}

def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()

def snapshot(connection, keys=None):
    selected = CHECKS if keys is None else {name: CHECKS[name] for name in keys}
    return {name: [str(value) for value in connection.execute(sql).fetchone()] for name, sql in selected.items()}

def create_backup():
    key = Path(os.environ['BACKUP_KEY_FILE']).resolve(strict=True)
    if key.stat().st_size < 32:
        raise SystemExit('Backup key must contain at least 32 bytes and be kept outside the repository.')
    destination = Path(os.environ.get('BACKUP_DIR', ROOT / 'backups')).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = destination / f'productstat-{stamp}.tar.gpg'
    with tempfile.TemporaryDirectory(prefix='productstat-backup-') as temp:
        work = Path(temp)
        dump = work / 'database.dump'
        with psycopg.connect() as connection:
            connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            exported = connection.execute('SELECT pg_export_snapshot()').fetchone()[0]
            totals = snapshot(connection)
            subprocess.run(['pg_dump', '--snapshot', exported, '--format=custom', '--no-owner', '--no-acl', '--file', str(dump)], check=True)
        media = Path(os.environ.get('MEDIA_ROOT', ROOT / 'backend' / 'private_media')).resolve()
        files = [path for path in media.rglob('*') if path.is_file() and not path.is_symlink()] if media.is_dir() else []
        checksums = {str(path.relative_to(media)): digest(path) for path in files}
        manifest = {'created_at': stamp, 'database_sha256': digest(dump), 'format': 2,
                    'database_checks': totals, 'media_sha256': checksums}
        (work / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        archive = work / 'backup.tar'
        with tarfile.open(archive, 'w') as tar:
            tar.add(dump, arcname='database.dump')
            tar.add(work / 'manifest.json', arcname='manifest.json')
            for path in files:
                tar.add(path, arcname='private_media/' + str(path.relative_to(media)), recursive=False)
        subprocess.run(['gpg', '--batch', '--yes', '--pinentry-mode', 'loopback', '--passphrase-file', str(key),
                        '--symmetric', '--cipher-algo', 'AES256', '--output', str(output), str(archive)], check=True)
    output.chmod(0o600)
    return {'file': str(output), 'sha256': digest(output), 'encrypted': True,
            'database_checks': totals, 'private_files': len(checksums)}

if __name__ == '__main__':
    try:
        print(json.dumps(create_backup()))
    except KeyError as exc:
        raise SystemExit(f'Missing required environment variable: {exc.args[0]}') from exc

