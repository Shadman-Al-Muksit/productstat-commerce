import csv
import io
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import OperationalError
from django.utils import timezone
from rest_framework.test import APIClient

from commerce.imports import SCHEMAS, commit_batch, stage_upload, validate_batch
from commerce.models import ImportBatch, Order, OrderLine, OutboxEvent, PaymentSettlement, Product, Refund, ReturnRequest, Shipment, SKU, StockMovement
from commerce.tasks import deliver_outbox


def upload(kind, rows, name=None):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=SCHEMAS[kind])
    writer.writeheader()
    writer.writerows(rows)
    return SimpleUploadedFile(name or f"{kind}.csv", stream.getvalue().encode(), content_type="text/csv")


@pytest.fixture
def import_data(db):
    product = Product.objects.create(name="Import product", slug="import-product", category="Testing")
    sku = SKU.objects.create(product=product, code="IMPORT-1", price=100, on_hand=100)
    actor = get_user_model().objects.create_user(username="importer", role="administrator", is_staff=True)
    return sku, actor


def history_row(**changes):
    row = {"source_order_id": "OLD-1", "source_line_id": "1", "sku": "IMPORT-1", "ordered_at": "2026-01-01T12:00:00+06:00",
           "status": "delivered", "payment_method": "cod", "quantity": "2", "unit_price": "100.00", "discount_total": "0",
           "cancelled_quantity": "0", "shipped_quantity": "2", "delivered_quantity": "2", "delivered_at": "2026-01-03T12:00:00+06:00",
           "returned_quantity": "1", "returned_at": "2026-01-05T12:00:00+06:00", "refund_amount": "100.00", "refunded_at": "2026-01-06T12:00:00+06:00",
           "collected_amount": "200.00", "collected_at": "2026-01-03T12:00:00+06:00", "settled_amount": "200.00", "settled_at": "2026-01-04T12:00:00+06:00"}
    return {**row, **changes}


def test_history_repeat_is_idempotent_and_does_not_change_stock(import_data, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    sku, actor = import_data
    for attempt in range(2):
        batch = stage_upload(kind="history", source_name="legacy", files=[upload("history", [history_row()])], actor=actor)
        assert validate_batch(batch.id).status == "ready"
        committed = commit_batch(batch.id)
        assert committed.status == "completed"
        assert committed.result["created" if attempt == 0 else "skipped"] == 1
    assert Order.objects.filter(source="csv:legacy").count() == 1
    assert OrderLine.objects.count() == 1
    assert PaymentSettlement.objects.count() == 1
    assert PaymentSettlement.objects.get().amount == 200
    assert PaymentSettlement.objects.get().source == "import"
    sku.refresh_from_db()
    assert sku.on_hand == 100
    assert sku.reserved == 0
    assert StockMovement.objects.count() == 0


def test_positive_delivery_requires_timestamp(import_data, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    _, actor = import_data
    batch = stage_upload(kind="history", source_name="missing-time", files=[upload("history", [history_row(delivered_at="")])], actor=actor)
    checked = validate_batch(batch.id)
    assert checked.status == "failed"
    assert "delivered_at" in checked.errors[0]["message"]
    assert Order.objects.count() == 0


def test_related_history_csv_batch_and_repeat(import_data, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    _, actor = import_data
    for attempt in range(2):
        files = [upload("orders", [{"source_order_id": "RELATED-1", "ordered_at": "2026-01-01T12:00:00+06:00", "status": "delivered", "payment_method": "cod", "shipping_total": "0"}]),
                 upload("lines", [{"source_order_id": "RELATED-1", "source_line_id": "L1", "sku": "IMPORT-1", "quantity": "1", "unit_price": "100", "discount_total": "0", "cancelled_quantity": "0"}]),
                 upload("shipments", [{"source_order_id": "RELATED-1", "source_line_id": "L1", "source_shipment_id": "S1", "state": "delivered", "quantity": "1", "dispatched_at": "2026-01-02T12:00:00+06:00", "completed_at": "2026-01-03T12:00:00+06:00"}]),
                 upload("payments", [{"source_order_id": "RELATED-1", "source_payment_id": "P1", "method": "cod", "amount": "100", "collected_at": "2026-01-03T12:00:00+06:00", "settled_amount": "0", "settled_at": ""}])]
        batch = stage_upload(kind="history", source_name="related", files=files, actor=actor)
        assert validate_batch(batch.id).status == "ready"
        assert commit_batch(batch.id).status == "completed"
    assert Order.objects.count() == 1


def test_stock_commit_rolls_back_all_rows_if_later_adjustment_invalid(import_data, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    sku, actor = import_data
    batch = stage_upload(kind="adjustments", source_name="stock", files=[upload("adjustments", [
        {"source_record_id": "A1", "sku": sku.code, "quantity_delta": "5", "reason": "Count correction"},
        {"source_record_id": "A2", "sku": sku.code, "quantity_delta": "-999", "reason": "Invalid count"}])], actor=actor)
    assert validate_batch(batch.id).status == "ready"
    assert commit_batch(batch.id).status == "failed"
    sku.refresh_from_db()
    assert sku.on_hand == 100
    assert StockMovement.objects.count() == 0


def test_analyst_cannot_import(import_data):
    analyst = get_user_model().objects.create_user(username="read-only", role="analyst", is_staff=True)
    client = APIClient()
    client.force_authenticate(analyst)
    assert client.get("/api/v1/imports/").status_code == 403


def related_files(*, duplicate_payment=False, inconsistent_shipment=False):
    order = {"source_order_id": "SHARED", "ordered_at": "2026-01-01T12:00:00+06:00", "status": "delivered", "payment_method": "cod", "shipping_total": "0"}
    line_rows = [{"source_order_id": "SHARED", "source_line_id": str(index), "sku": "IMPORT-1", "quantity": "1", "unit_price": "100", "discount_total": "0", "tax_total": "0", "cancelled_quantity": "0"} for index in (1, 2)]
    shipments = [{"source_order_id": "SHARED", "source_line_id": str(index), "source_shipment_id": "PACKAGE-1", "state": "delivered", "quantity": "1", "dispatched_at": "2026-01-02T12:00:00+06:00", "completed_at": "2026-01-03T12:00:00+06:00"} for index in (1, 2)]
    if inconsistent_shipment:
        shipments[1]["completed_at"] = "2026-01-04T12:00:00+06:00"
    returns = [{"source_order_id": "SHARED", "source_line_id": str(index), "source_return_id": "RETURN-1", "quantity": "1", "accepted_quantity": "1", "received_at": "2026-01-05T12:00:00+06:00", "inspected_at": "2026-01-05T14:00:00+06:00", "disposition": "quarantine"} for index in (1, 2)]
    refunds = [{"source_order_id": "SHARED", "source_line_id": str(index), "source_refund_id": "REFUND-1", "amount": "100", "tax_amount": "0", "shipping_amount": "0", "confirmed_at": "2026-01-06T12:00:00+06:00"} for index in (1, 2)]
    payment = {"source_order_id": "SHARED", "source_payment_id": "COLLECTION-1", "method": "cod", "amount": "200", "collected_at": "2026-01-03T12:00:00+06:00", "settled_amount": "200", "settled_at": "2026-01-04T12:00:00+06:00"}
    return [upload("orders", [order]), upload("lines", line_rows), upload("shipments", shipments), upload("returns", returns), upload("refunds", refunds), upload("payments", [payment, payment] if duplicate_payment else [payment])]


def test_shared_history_events_group_without_inflating_shipments(import_data, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    _, actor = import_data
    batch = stage_upload(kind="history", source_name="shared", files=related_files(), actor=actor)
    assert validate_batch(batch.id).status == "ready"
    result = commit_batch(batch.id)
    assert result.status == "completed", result.errors
    assert Shipment.objects.count() == 1
    assert Shipment.objects.first().lines.count() == 2
    assert ReturnRequest.objects.count() == 1
    assert ReturnRequest.objects.first().lines.count() == 2
    assert Refund.objects.count() == 1
    assert Refund.objects.first().amount == 200
    assert Refund.objects.first().lines.count() == 2


@pytest.mark.parametrize("changes,expected", [({"duplicate_payment": True}, "duplicate source_payment_id"), ({"inconsistent_shipment": True}, "inconsistent metadata")])
def test_shared_event_metadata_and_payment_duplicates_fail_before_commit(import_data, settings, tmp_path, changes, expected):
    settings.MEDIA_ROOT = tmp_path
    _, actor = import_data
    batch = stage_upload(kind="history", source_name="invalid-events", files=related_files(**changes), actor=actor)
    checked = validate_batch(batch.id)
    assert checked.status == "failed"
    assert expected in checked.errors[0]["message"]
    assert Order.objects.count() == 0


def test_conflicting_order_metadata_fails_validation(import_data, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    _, actor = import_data
    batch = stage_upload(kind="history", source_name="conflict", files=[upload("history", [history_row(), history_row(source_line_id="2", ordered_at="2026-01-02T12:00:00+06:00")])], actor=actor)
    checked = validate_batch(batch.id)
    assert checked.status == "failed"
    assert "inconsistent" in checked.errors[0]["message"]
    assert Order.objects.count() == 0


def test_outbox_backoff_does_not_exhaust_retries_in_one_invocation(import_data, settings):
    settings.PRODUCTSTAT_DEMO = False
    event = OutboxEvent.objects.create(kind="order_confirmation", payload={"to": "buyer@example.invalid", "subject": "Test", "body": "Test"})
    with patch("commerce.tasks.send_mail", side_effect=OSError("temporary mail outage")):
        assert deliver_outbox() == 1
        assert deliver_outbox() == 0
    event.refresh_from_db()
    assert event.attempts == 1
    assert event.status == "failed"
    assert event.next_attempt_at > timezone.now()
    OutboxEvent.objects.filter(pk=event.pk).update(next_attempt_at=timezone.now() - timedelta(seconds=1))
    with patch("commerce.tasks.send_mail", return_value=1):
        assert deliver_outbox() == 1
    event.refresh_from_db()
    assert event.status == "sent"
    assert event.attempts == 2


def test_demo_never_sends_old_queued_external_notifications(import_data, settings):
    settings.PRODUCTSTAT_DEMO = True
    event = OutboxEvent.objects.create(kind="order_confirmation", payload={"to": "buyer@example.invalid", "subject": "Test", "body": "Test"})
    with patch("commerce.tasks.send_mail") as sender:
        assert deliver_outbox() == 1
        sender.assert_not_called()
    event.refresh_from_db()
    assert event.status == "sent"
    assert event.last_error == "Suppressed in demo"


def test_expired_worker_claim_recovers_commit_without_duplicate_effects(import_data, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    _, actor = import_data
    batch = stage_upload(kind="history", source_name="crash-recovery", files=[upload("history", [history_row()])], actor=actor)
    assert validate_batch(batch.id).status == "ready"
    ImportBatch.objects.filter(pk=batch.pk).update(status="committing")
    event = OutboxEvent.objects.create(kind="import_commit", payload={"batch_id": str(batch.id)}, status="processing", attempts=1,
                                       next_attempt_at=timezone.now() - timedelta(seconds=1))
    assert deliver_outbox() == 1
    assert Order.objects.count() == 1
    OutboxEvent.objects.create(kind="import_commit", payload={"batch_id": str(batch.id)})
    assert deliver_outbox() == 1
    assert Order.objects.count() == 1
    event.refresh_from_db()
    assert event.status == "sent"


def test_transient_database_failure_remains_retryable(import_data, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    _, actor = import_data
    batch = stage_upload(kind="history", source_name="db-recovery", files=[upload("history", [history_row()])], actor=actor)
    assert validate_batch(batch.id).status == "ready"
    event = OutboxEvent.objects.create(kind="import_commit", payload={"batch_id": str(batch.id)})
    with patch("commerce.imports._create_history_order", side_effect=OperationalError("temporary database outage")):
        assert deliver_outbox() == 1
    assert Order.objects.count() == 0
    event.refresh_from_db()
    assert event.status == "failed"
    assert event.attempts == 1
    OutboxEvent.objects.filter(pk=event.pk).update(next_attempt_at=timezone.now() - timedelta(seconds=1))
    assert deliver_outbox() == 1
    assert Order.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_upload_and_commit_survive_broker_outage(import_data, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    _, actor = import_data
    client = APIClient()
    client.force_authenticate(actor)
    with patch("commerce.tasks.deliver_outbox.delay", side_effect=OSError("broker offline")):
        response = client.post("/api/v1/imports/", {"kind": "history", "source_name": "broker-outage", "file": upload("history", [history_row()])}, format="multipart")
        assert response.status_code == 202
        batch_id = response.json()["id"]
        assert OutboxEvent.objects.filter(status="pending").count() == 1
        assert deliver_outbox() == 1
        assert ImportBatch.objects.get(pk=batch_id).status == "ready"
        assert client.post(f"/api/v1/imports/{batch_id}/commit/").status_code == 202
        assert deliver_outbox() == 1
    assert Order.objects.count() == 1
    assert client.post(f"/api/v1/imports/{batch_id}/commit/").status_code == 200
    assert Order.objects.count() == 1


def test_opening_stock_cannot_reset_sku_with_live_order_history(import_data, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    sku, actor = import_data
    sku.on_hand = 0
    sku.save(update_fields=["on_hand"])
    order = Order.objects.create(number="LIVE-HISTORY", customer_name="Synthetic", email="buyer@example.invalid", phone="")
    OrderLine.objects.create(order=order, sku=sku, sku_code=sku.code, product_name=sku.product.name, quantity=1, unit_price=100)
    batch = stage_upload(kind="opening_stock", source_name="forbidden-reset", files=[upload("opening_stock", [{"source_record_id": "FIRST", "sku": sku.code, "quantity": "100"}])], actor=actor)
    assert validate_batch(batch.id).status == "ready"
    result = commit_batch(batch.id)
    assert result.status == "failed"
    sku.refresh_from_db()
    assert sku.on_hand == 0
