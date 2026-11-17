"""Short shared cache for HTTP overviews, versioned by committed business writes.

The analytical query itself stays uncached. Audit rows are append-only through all
supported write paths; their COUNT catches even an older audit timestamp committed
after a newer transaction. Imports carry a second committed revision as a safeguard.
"""
import hashlib
import json
import logging
import time

from django.core.cache import caches
from django.db.models import Count, Max

from .models import AuditEvent, ImportBatch

CACHE_SECONDS = 30
LOCK_SECONDS = 10
WAIT_SECONDS = 1.8
logger = logging.getLogger(__name__)


def get_cache():
    return caches["reporting"]


def revision_key(filters):
    audit = AuditEvent.objects.aggregate(count=Count("pk"), latest=Max("created_at"))
    imports = ImportBatch.objects.filter(status="completed").aggregate(count=Count("pk"), latest=Max("committed_at"))
    facts = {"schema": 3, "start": filters["start"].isoformat(), "end": filters["end"].isoformat(),
             "products": sorted(set(filters["product_ids"])), "audit": audit, "imports": imports}
    digest = hashlib.sha256(json.dumps(facts, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
    return "overview:" + digest


def _unavailable(exc):
    # Never log cache URLs, credentials or response payloads.
    logger.warning("reporting_cache_unavailable: %s", type(exc).__name__)


def cached_overview(filters, calculate):
    """Return (payload, cache status); a Redis fault falls back to the database.

    Lock expiry is automatic. We intentionally do not delete locks with a racy
    compare/delete: successful cached data outlives its lock, and revisions get
    independent keys. Waiting is bounded so a dead owner cannot stall requests.
    """
    key = revision_key(filters)
    try:
        cache = get_cache()
        payload = cache.get(key)
        if payload is not None:
            return payload, "HIT"
        owner = cache.add(key + ":lock", True, timeout=LOCK_SECONDS)
    except Exception as exc:
        _unavailable(exc)
        return calculate(filters), "BYPASS"
    if not owner:
        deadline = time.monotonic() + WAIT_SECONDS
        while time.monotonic() < deadline:
            time.sleep(.025)
            try:
                payload = cache.get(key)
            except Exception as exc:
                _unavailable(exc)
                return calculate(filters), "BYPASS"
            if payload is not None:
                return payload, "WAIT-HIT"
        # A crashed or unusually slow lock owner must not make the report unavailable.
        return calculate(filters), "LOCK-TIMEOUT"
    payload = calculate(filters)
    try:
        cache.set(key, payload, timeout=CACHE_SECONDS)
    except Exception as exc:
        _unavailable(exc)
        return payload, "BYPASS"
    return payload, "MISS"
