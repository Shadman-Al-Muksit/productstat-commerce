"""Cache ownership behavior without real delays, Redis, or database writes."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from rest_framework.views import exception_handler

from commerce import reporting_cache


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class LeaseCache:
    """An expiring atomic-add cache with an optional other-owner publication."""
    def __init__(self, clock, publish_at=None):
        self.clock = clock
        self.publish_at = publish_at
        self.values = {}
        self.writes = []

    def get(self, key):
        if key == "report" and self.publish_at is not None and self.clock.now >= self.publish_at:
            return {"owner": "original"}
        value, expiry = self.values.get(key, (None, 0))
        return value if self.clock.now < expiry else None

    def add(self, key, value, timeout):
        if self.get(key) is not None:
            return False
        self.values[key] = (value, self.clock.now + timeout)
        return True

    def set(self, key, value, timeout):
        self.writes.append((key, value, timeout))
        self.values[key] = (value, self.clock.now + timeout)


@pytest.fixture
def cache_setup(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(reporting_cache, "time", SimpleNamespace(monotonic=clock.monotonic, sleep=clock.sleep))
    monkeypatch.setattr(reporting_cache, "revision_key", lambda filters: "report")

    def install(cache):
        monkeypatch.setattr(reporting_cache, "get_cache", lambda: cache)
        return cache

    return clock, install


def test_cold_owner_keeps_exact_thirty_second_payload_ttl(cache_setup):
    clock, install = cache_setup
    cache = install(LeaseCache(clock))
    calculate = Mock(return_value={"owner": "new"})
    assert reporting_cache.cached_overview({}, calculate) == ({"owner": "new"}, "MISS")
    assert cache.writes == [("report", {"owner": "new"}, 30)]
    assert reporting_cache.CACHE_SECONDS == 30
    assert reporting_cache.cached_overview({}, calculate) == ({"owner": "new"}, "HIT")
    calculate.assert_called_once_with({})


def test_waiter_does_not_duplicate_normal_cold_query_over_old_wait_limit(cache_setup):
    clock, install = cache_setup
    cache = install(LeaseCache(clock, publish_at=2.6))
    cache.add("report:lock", True, timeout=reporting_cache.LOCK_SECONDS)
    calculate = Mock()
    assert reporting_cache.cached_overview({}, calculate) == ({"owner": "original"}, "WAIT-HIT")
    assert 2.6 <= clock.now < 2.7
    calculate.assert_not_called()


def test_expired_owner_is_replaced_once_then_other_waiters_hit(cache_setup):
    clock, install = cache_setup
    cache = install(LeaseCache(clock))
    cache.add("report:lock", True, timeout=reporting_cache.LOCK_SECONDS)
    calculate = Mock(return_value={"owner": "replacement"})
    assert reporting_cache.cached_overview({}, calculate) == ({"owner": "replacement"}, "TAKEOVER")
    assert reporting_cache.LOCK_SECONDS <= clock.now < reporting_cache.LOCK_SECONDS + .1
    assert reporting_cache.cached_overview({}, calculate) == ({"owner": "replacement"}, "HIT")
    calculate.assert_called_once_with({})


@pytest.mark.parametrize("waiting", [False, True])
def test_publication_during_lock_acquisition_avoids_duplicate(cache_setup, waiting):
    clock, install = cache_setup

    class RacingCache(LeaseCache):
        def add(self, key, value, timeout):
            owner = super().add(key, value, timeout)
            if owner:
                self.set("report", {"owner": "original"}, 30)
            return owner

    cache = install(RacingCache(clock))
    if waiting:
        cache.values["report:lock"] = (True, reporting_cache.LOCK_SECONDS)
    calculate = Mock()
    assert reporting_cache.cached_overview({}, calculate) == ({"owner": "original"}, "WAIT-HIT" if waiting else "HIT")
    calculate.assert_not_called()


def test_continually_occupied_lease_has_bounded_503_without_database_fanout(cache_setup):
    clock, install = cache_setup

    class BusyCache(LeaseCache):
        def add(self, key, value, timeout):
            return False

    install(BusyCache(clock))
    calculate = Mock()
    with pytest.raises(reporting_cache.ReportInProgress) as caught:
        reporting_cache.cached_overview({}, calculate)
    assert clock.now == pytest.approx(reporting_cache.WAIT_SECONDS)
    calculate.assert_not_called()
    response = exception_handler(caught.value, {})
    assert response.status_code == 503
    assert response["Retry-After"] == "1"


@pytest.mark.parametrize("failure_stage", ["get", "wait", "set"])
def test_cache_faults_preserve_database_fallback_and_redact_exception(cache_setup, caplog, failure_stage):
    clock, install = cache_setup

    class FaultyCache(LeaseCache):
        def get(self, key):
            if failure_stage == "get" or failure_stage == "wait" and clock.now:
                raise RuntimeError("redis://private-password@private-host/1")
            return super().get(key)

        def set(self, key, value, timeout):
            if failure_stage == "set":
                raise RuntimeError("redis://private-password@private-host/1")
            return super().set(key, value, timeout)

    cache = install(FaultyCache(clock))
    if failure_stage == "wait":
        cache.add("report:lock", True, timeout=reporting_cache.LOCK_SECONDS)
    calculate = Mock(return_value={"owner": "database"})
    assert reporting_cache.cached_overview({}, calculate) == ({"owner": "database"}, "BYPASS")
    calculate.assert_called_once_with({})
    assert "RuntimeError" in caplog.text
    assert "private-password" not in caplog.text and "private-host" not in caplog.text


def test_failed_calculation_lease_expires_before_takeover(cache_setup):
    clock, install = cache_setup
    install(LeaseCache(clock))
    with pytest.raises(ValueError, match="query failed"):
        reporting_cache.cached_overview({}, Mock(side_effect=ValueError("query failed")))
    calculate = Mock(return_value={"owner": "replacement"})
    assert reporting_cache.cached_overview({}, calculate) == ({"owner": "replacement"}, "TAKEOVER")
    assert reporting_cache.LOCK_SECONDS <= clock.now < reporting_cache.LOCK_SECONDS + .1
    calculate.assert_called_once_with({})
