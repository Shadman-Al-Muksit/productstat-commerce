"""Create private synthetic read-only benchmark sessions; never include them in evidence."""
import datetime as dt
import json
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.contrib.auth import SESSION_KEY, BACKEND_SESSION_KEY, HASH_SESSION_KEY, get_user_model
from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore
from django.utils import timezone

if not settings.PRODUCTSTAT_DEMO:
    raise SystemExit('Load identities are permitted only in the synthetic demonstration environment.')
payload = {'customers': [], 'staff': []}
for role, count, group in [('customer', 20, 'customers'), ('analyst', 5, 'staff')]:
    for index in range(count):
        user, created = get_user_model().objects.get_or_create(
            username=f'synthetic_load_{role}_{index + 1}', defaults={'role': role})
        if not created and user.role != role:
            raise SystemExit('Existing benchmark identity has unexpected permissions; inspect it before continuing.')
        user.set_unusable_password()
        user.save(update_fields=['password'])
        session = SessionStore()
        session[SESSION_KEY] = str(user.pk)
        session[BACKEND_SESSION_KEY] = 'django.contrib.auth.backends.ModelBackend'
        session[HASH_SESSION_KEY] = user.get_session_auth_hash()
        session.set_expiry(3600)
        session.save()
        payload[group].append(session.session_key)
today = timezone.localdate()
payload.update(start=(today - dt.timedelta(days=365)).isoformat(), end=today.isoformat())
target = root / '.runtime' / 'load-auth.json'
target.write_text(json.dumps(payload), encoding='utf-8')
target.chmod(0o600)
print('Prepared 20 customer and five analyst identities with private benchmark sessions (not logged).')
