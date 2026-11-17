"""Small Celery surface backed by durable database outbox events."""
from celery import shared_task
from datetime import timedelta
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import OutboxEvent


@shared_task
def expire_reservations():
    from .services import expire_reservations as expire
    return expire()


@shared_task
def validate_import(batch_id):
    from .imports import validate_batch
    return str(validate_batch(batch_id).status)


@shared_task
def commit_import(batch_id):
    from .imports import commit_batch
    return str(commit_batch(batch_id).status)


@shared_task
def deliver_outbox(limit=20):
    processed = 0
    for _ in range(min(limit, 100)):
        now = timezone.now()
        with transaction.atomic():
            event = OutboxEvent.objects.select_for_update(skip_locked=True).filter(
                status__in=["pending", "failed", "processing"], attempts__lt=8).filter(
                Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now)).order_by("created_at").first()
            if event is None:
                break
            event.attempts += 1
            event.status = "processing"
            event.next_attempt_at = now + timedelta(minutes=5)
            event.save(update_fields=["attempts", "status", "next_attempt_at"])
        # Do work after the short claim transaction. Import functions own their atomicity.
        # A dead worker's five-minute lease expires and its idempotent import resumes.
        try:
            suppressed = False
            if event.kind == "import_validate":
                from .imports import validate_batch
                validate_batch(event.payload["batch_id"])
            elif event.kind == "import_commit":
                from .imports import commit_batch
                commit_batch(event.payload["batch_id"])
            elif event.kind in {"order_confirmation", "order_update", "return_update"}:
                if settings.PRODUCTSTAT_DEMO:
                    suppressed = True
                elif event.payload.get("to"):
                    send_mail(event.payload["subject"], event.payload["body"], settings.DEFAULT_FROM_EMAIL, [event.payload["to"]], fail_silently=False)
            else:
                raise ValueError("Unsupported outbox event kind.")
            OutboxEvent.objects.filter(pk=event.pk, attempts=event.attempts, status="processing").update(
                status="sent", sent_at=timezone.now(), next_attempt_at=None,
                last_error="Suppressed in demo" if suppressed else "")
        except Exception as exc:
            OutboxEvent.objects.filter(pk=event.pk, attempts=event.attempts, status="processing").update(
                status="failed", last_error=str(exc)[:500],
                next_attempt_at=timezone.now() + timedelta(seconds=min(30 * 2 ** (event.attempts - 1), 900)))
            if event.attempts >= 8 and event.kind in {"import_validate", "import_commit"}:
                from .models import ImportBatch
                ImportBatch.objects.filter(pk=event.payload.get("batch_id")).exclude(status="completed").update(
                    status="failed", progress=100, errors=[{"row": None, "message": "Worker retries exhausted; an administrator must inspect the durable outbox and retry."}])
        processed += 1
    return processed
