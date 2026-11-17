#!/usr/bin/env python3
"""Exercise real HTTP imports and a separately owned Celery worker, then compensate stock."""
import csv
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4

import requests

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402
django.setup()
from commerce.models import OutboxEvent, StockMovement  # noqa: E402


class Worker:
    def __init__(self):
        self.process = None
        self.records = []

    def start(self):
        if self.process and self.process.poll() is None:
            return
        command = [sys.executable, "-m", "celery", "-A", "config", "worker", "--pool=solo", "--concurrency=1",
                   "--loglevel=WARNING", "--without-gossip", "--without-mingle", "--without-heartbeat",
                   "--hostname", f"async-verification-{os.getpid()}@%h", "--prefetch-multiplier=1"]
        self.process = subprocess.Popen(command, cwd=PROJECT / "backend", env=os.environ.copy(),
                                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL, start_new_session=True)
        self.records.append({"pid": self.process.pid, "started_at": datetime.now(timezone.utc).isoformat(), "stopped": False})

    def stop(self):
        if self.process is None:
            return
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=5)
        # Stop any descendant in the owned session, including unexpected pool children.
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        self.records[-1]["stopped"] = True
        self.records[-1]["exit_code"] = self.process.returncode
        self.process = None


class Client:
    def __init__(self):
        self.base = os.getenv("PRODUCTSTAT_API_URL", "http://127.0.0.1:8001").rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Origin": self.base, "Referer": self.base + "/"})
        bootstrap = self.request("GET", "bootstrap/")
        self.session.headers["X-CSRFToken"] = bootstrap["csrfToken"]
        auth = self.request("POST", "auth/login/", json={"username": os.getenv("DEMO_ADMIN_USERNAME", "administrator"),
                                                          "password": os.getenv("DEMO_PASSWORD", "ProductStatDemo!2026")})
        self.session.headers["X-CSRFToken"] = auth["csrfToken"]

    def request(self, method, path, **kwargs):
        response = self.session.request(method, self.base + "/api/v1/" + path, timeout=20, **kwargs)
        if not response.ok:
            raise RuntimeError(f"{method} {path}: HTTP {response.status_code}: {response.text[:500]}")
        return response.json()

    def upload(self, source, sku, record_id, delta):
        content = io.StringIO()
        writer = csv.writer(content)
        writer.writerow(["source_record_id", "sku", "quantity_delta", "reason"])
        writer.writerow([record_id, sku, delta, "Automated async integration verification; compensated in the same run"])
        return self.request("POST", "imports/", data={"kind": "adjustments", "source_name": source},
                            files={"file": ("adjustments.csv", content.getvalue().encode(), "text/csv")})

    def wait(self, batch_id, status, worker, timeout=90):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            batch = self.request("GET", f"imports/{batch_id}/")
            if batch["status"] == status:
                return batch
            if batch["status"] == "failed":
                raise RuntimeError(f"Batch {batch_id} failed: {batch['errors']}")
            if worker.process and worker.process.poll() is not None:
                raise RuntimeError(f"Owned Celery worker exited with code {worker.process.returncode}")
            time.sleep(.3)
        raise TimeoutError(f"Batch {batch_id} did not reach {status}; last state {batch['status']}")

    def commit(self, batch_id, worker):
        current = self.request("GET", f"imports/{batch_id}/")
        if current["status"] == "completed":
            return current
        if current["status"] != "committing":
            self.wait(batch_id, "ready", worker)
            self.request("POST", f"imports/{batch_id}/commit/", json={})
        return self.wait(batch_id, "completed", worker)

    def inventory(self, sku):
        rows = self.request("GET", "staff/inventory/?q=" + requests.utils.quote(sku) + "&page_size=100")["results"]
        return next(row for row in rows if row["code"] == sku)


def snapshot(row):
    return {"on_hand": row["on_hand"], "reserved": row["reserved"], "available": row["available"]}


def main():
    worker = Worker()
    client = None
    source = "verification-async-" + uuid4().hex[:10]
    evidence = {"status": "running", "source_name": source, "real_worker": True, "batches": [], "workers": worker.records}
    sku = baseline = None
    cleanup_batch = None
    failure = None
    try:
        if os.getenv("CELERY_TASK_ALWAYS_EAGER", "0") == "1":
            raise RuntimeError("Real-worker verification cannot run with CELERY_TASK_ALWAYS_EAGER=1.")
        client = Client()
        inventory = client.request("GET", "staff/inventory/?page_size=100")["results"]
        selected = next(row for row in inventory if row["code"].startswith("FRM-") and row["on_hand"] >= 20 and row["reserved"] == 0)
        sku = selected["code"]
        baseline = snapshot(selected)
        evidence.update(base_url=client.base, sku=sku, baseline=baseline)
        print(f"Verifying real async imports on {sku}; starting on-hand {baseline['on_hand']}.", flush=True)

        first = client.upload(source, sku, "increase-once", 1)
        evidence["queued_before_worker"] = first["status"]
        assert client.request("GET", f"imports/{first['id']}/")["status"] == "queued", "Another worker or eager execution processed the batch before our worker started."
        worker.start()
        first = client.commit(first["id"], worker)
        evidence["batches"].append(first)
        evidence["after_first"] = snapshot(client.inventory(sku))
        assert evidence["after_first"]["on_hand"] == baseline["on_hand"] + 1
        assert first["result"] == {"created": 1, "updated": 0, "skipped": 0}

        repeated = client.upload(source, sku, "increase-once", 1)
        repeated = client.commit(repeated["id"], worker)
        evidence["batches"].append(repeated)
        evidence["after_repeat"] = snapshot(client.inventory(sku))
        assert repeated["result"] == {"created": 0, "updated": 0, "skipped": 1}
        assert evidence["after_repeat"] == evidence["after_first"]
        assert StockMovement.objects.filter(kind="import_adjustments", reference=f"csv:{source}:increase-once").count() == 1

        worker.stop()
        cleanup_batch = client.upload(source, sku, "cleanup-once", -1)
        time.sleep(1)
        queued = client.request("GET", f"imports/{cleanup_batch['id']}/")
        assert queued["status"] == "queued"
        pending = OutboxEvent.objects.filter(kind="import_validate", payload__batch_id=cleanup_batch["id"], status="pending").exists()
        assert pending, "Worker-down upload did not retain its durable pending outbox event."
        evidence["worker_restart"] = {"queued_batch_id": cleanup_batch["id"], "status_while_stopped": queued["status"],
                                       "durable_pending_event": pending}
        worker.start()
        cleanup_batch = client.commit(cleanup_batch["id"], worker)
        evidence["batches"].append(cleanup_batch)
        evidence["worker_restart"]["status_after_restart"] = cleanup_batch["status"]
        evidence["final"] = snapshot(client.inventory(sku))
        assert evidence["final"] == baseline
        movements = list(StockMovement.objects.filter(kind="import_adjustments", reference__startswith=f"csv:{source}:").values("id", "reference", "on_hand_delta"))
        assert len(movements) == 2 and sum(row["on_hand_delta"] for row in movements) == 0
        evidence["stock_movements"] = [{**row, "id": str(row["id"])} for row in movements]
        evidence["status"] = "passed"
        print("Passed: real worker validation/commit, duplicate skip, worker restart, and compensated stock.", flush=True)
    except Exception as exc:
        failure = exc
        evidence["status"] = "failed"
        evidence["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        # Compensate only this run's own +1, using the same audited/idempotent CSV path.
        if client and sku:
            increase_exists = StockMovement.objects.filter(kind="import_adjustments", reference=f"csv:{source}:increase-once").exists()
            cleanup_exists = StockMovement.objects.filter(kind="import_adjustments", reference=f"csv:{source}:cleanup-once").exists()
            if increase_exists and not cleanup_exists:
                try:
                    worker.start()
                    if not cleanup_batch or cleanup_batch["status"] == "failed":
                        cleanup_batch = client.upload(source, sku, "cleanup-once", -1)
                    cleaned = client.commit(cleanup_batch["id"], worker)
                    evidence["emergency_compensation"] = {"id": cleaned["id"], "status": cleaned["status"]}
                except Exception as exc:
                    evidence["compensation_error"] = f"{type(exc).__name__}: {exc}"
            try:
                evidence["final"] = snapshot(client.inventory(sku))
            except Exception as exc:
                evidence["final_snapshot_error"] = f"{type(exc).__name__}: {exc}"
        worker.stop()
        evidence["recorded_at"] = datetime.now(timezone.utc).isoformat()
        # Keep only verification facts; exclude cookies, headers, credentials and customer data.
        evidence["batches"] = [{key: batch[key] for key in ("id", "kind", "status", "source_name", "result", "total_rows", "valid_rows", "error_rows")} for batch in evidence["batches"]]
        output = PROJECT / ".runtime" / "async-evidence.json"
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(f"Evidence: {output}", flush=True)
    if failure:
        raise RuntimeError(evidence["error"]) from failure


if __name__ == "__main__":
    main()
