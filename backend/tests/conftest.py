"""Tests isolate rate-limit histories; production workers use shared Redis DB2."""
from uuid import uuid4
import pytest

@pytest.fixture(autouse=True)
def isolated_default_cache(settings):
    settings.CACHES={**settings.CACHES,'default':{'BACKEND':'django.core.cache.backends.locmem.LocMemCache','LOCATION':'test-throttles-'+uuid4().hex}}
