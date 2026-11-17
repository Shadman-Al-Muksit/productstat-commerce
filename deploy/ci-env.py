"""Ephemeral CI-only Compose environment; never print generated credentials."""
import os
from pathlib import Path
import secrets

if os.getenv('CI') != 'true':
    raise SystemExit('This helper only generates disposable GitHub Actions test configuration.')
root = Path(__file__).resolve().parents[1]
database_password = secrets.token_urlsafe(40)
values = {
    'PUBLIC_DOMAIN': 'localhost', 'DJANGO_DEBUG': '0', 'DJANGO_SECRET_KEY': secrets.token_urlsafe(60),
    'DJANGO_ALLOWED_HOSTS': 'localhost,127.0.0.1,backend,caddy',
    'DJANGO_CSRF_TRUSTED_ORIGINS': 'https://localhost', 'PUBLIC_APP_URL': 'https://localhost',
    'POSTGRES_DB': 'productstat', 'POSTGRES_USER': 'productstat', 'POSTGRES_PASSWORD': database_password,
    'PGDATABASE': 'productstat', 'PGUSER': 'productstat', 'PGPASSWORD': database_password,
    'PRODUCTSTAT_DEMO': '1', 'SSLCOMMERZ_SANDBOX': '1',
    'DEMO_PASSWORD': secrets.token_urlsafe(32), 'DEMO_VIEWER_PASSWORD': secrets.token_urlsafe(32),
    'EMAIL_BACKEND': 'django.core.mail.backends.dummy.EmailBackend',
    'BACKUP_DIR': './backups', 'BACKUP_KEY_FILE': './.runtime/backup-key',
}
target = root / '.env.production'
target.write_text(''.join(f'{key}={value}\n' for key, value in values.items()))
target.chmod(0o600)
(root / '.runtime').mkdir(exist_ok=True)
key = root / '.runtime' / 'backup-key'
key.write_text(secrets.token_urlsafe(64))
key.chmod(0o600)
(root / 'backups').mkdir(exist_ok=True)
print('Generated private, disposable container configuration.')
