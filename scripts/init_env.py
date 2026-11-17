import pathlib
import secrets
import sys

target = pathlib.Path(sys.argv[1])
if not target.exists():
    target.write_text('\n'.join([
        'DJANGO_DEBUG=1', 'DJANGO_SECRET_KEY=' + secrets.token_urlsafe(48),
        'DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,testserver',
        'DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000',
        'PGHOST=127.0.0.1', 'PGPORT=55433', 'PGDATABASE=productstat',
        'PGUSER=productstat', 'PGPASSWORD=' + secrets.token_urlsafe(32),
        'REDIS_URL=redis://127.0.0.1:56379/0',
        'CELERY_BROKER_URL=redis://127.0.0.1:56379/0',
        'CELERY_RESULT_BACKEND=redis://127.0.0.1:56379/1',
        'PRODUCTSTAT_DEMO=1', 'PUBLIC_APP_URL=http://localhost:3000',
        'EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend',
        'SSLCOMMERZ_STORE_ID=', 'SSLCOMMERZ_STORE_PASSWORD=',
        'SSLCOMMERZ_SANDBOX=1', 'NEXT_TELEMETRY_DISABLED=1', ''
    ]), encoding='utf-8')
    target.chmod(0o600)
