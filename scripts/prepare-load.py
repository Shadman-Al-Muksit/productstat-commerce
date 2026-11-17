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
from django.contrib.sessions.backends.db import SessionStore
from django.utils import timezone

payload = {}
for role in ['customer', 'analyst']:
    user = get_user_model().objects.get(username=role)
    session = SessionStore()
    session[SESSION_KEY] = str(user.pk)
    session[BACKEND_SESSION_KEY] = 'django.contrib.auth.backends.ModelBackend'
    session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    session.set_expiry(3600)
    session.save()
    payload[role] = session.session_key
today = timezone.localdate()
payload.update(start=(today - dt.timedelta(days=365)).isoformat(), end=today.isoformat())
target = root / '.runtime' / 'load-auth.json'
target.write_text(json.dumps(payload), encoding='utf-8')
target.chmod(0o600)
print('Prepared isolated benchmark sessions (not logged).')
