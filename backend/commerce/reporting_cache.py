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
from rest_framework.exceptions import APIException

from .models import AuditEvent, ImportBatch

CACHE_SECONDS = 30
LOCK_SECONDS = 10
# Allow the original lease to expire and a replacement owner to complete. The
# deadline stays finite even if owners repeatedly crash or take too long.
WAIT_SECONDS = LOCK_SECONDS * 2 + .25
POLL_SECONDS = .05
logger = logging.getLogger(__name__)


class ReportInProgress(APIException):
    status_code = 503
    default_detail = "The report is still being prepared. Retry shortly."
    default_code = "report_in_progress"
    wait = 1


def get_cache():
    return caches["reporting"]


def revision_key(filters):
    audit = AuditEvent.objects.aggregate(count=Count("pk"), latest=Max("created_at"))
    imports = ImportBatch.objects.filter(status="completed").aggregate(count=Count("pk"), latest=Max("committed_at"))
    facts = {"schema": 4, "start": filters["start"].isoformat(), "end": filters["end"].isoformat(),
             "products": sorted(set(filters["product_ids"])), "audit": audit, "imports": imports}
    digest = hashlib.sha256(json.dumps(facts, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
    return "overview:" + digest


def _unavailable(exc):
    # Never log cache URLs, credentials or response payloads.
    logger.warning("reporting_cache_unavailable: %s", type(exc).__name__)


def cached_overview(filters, calculate):
    """Return (payload, cache status); a Redis fault falls back to the database.

    Locks expire automatically; an atomic add elects one replacement after a
    crashed owner. Never delete a lock another worker may have acquired. Cache
    faults fall back to the database, but a healthy, occupied cache lease never
    triggers a second calculation merely because waiting took too long.
    """
    key = revision_key(filters)
    try:
        cache = get_cache()
        payload = cache.get(key)
        if payload is not None:
            return payload, "HIT"
        owner = cache.add(key + ":lock", True, timeout=LOCK_SECONDS)
        if owner:
            payload = cache.get(key)
            if payload is not None:
                return payload, "HIT"
    except Exception as exc:
        _unavailable(exc)
        return calculate(filters), "BYPASS"
    status = "MISS"
    if not owner:
        deadline = time.monotonic() + WAIT_SECONDS
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                # A second stuck owner must not fan out into database work.
                raise ReportInProgress()
            time.sleep(min(POLL_SECONDS, remaining))
            try:
                payload = cache.get(key)
                if payload is not None:
                    return payload, "WAIT-HIT"
                owner = cache.add(key + ":lock", True, timeout=LOCK_SECONDS)
                if owner:
                    # The earlier owner may have published just as its lease
                    # expired, between our read and the successful atomic add.
                    payload = cache.get(key)
                    if payload is not None:
                        return payload, "WAIT-HIT"
            except Exception as exc:
                _unavailable(exc)
                return calculate(filters), "BYPASS"
            if owner:
                status = "TAKEOVER"
                break
    payload = calculate(filters)
    try:
        cache.set(key, payload, timeout=CACHE_SECONDS)
    except Exception as exc:
        _unavailable(exc)
        return payload, "BYPASS"
    return payload, status
