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
from commerce.models import AuditEvent, ImportBatch, Order, OrderLine, OutboxEvent, Payment, PaymentSettlement, Product, Refund, ReturnRequest, Shipment, SKU, StockMovement
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


def test_unknown_historical_dates_remain_null_without_inventory_side_effects(import_data, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    _, actor = import_data
    batch = stage_upload(kind="history", source_name="missing-time", files=[upload("history", [history_row(ordered_at="", delivered_at="", returned_at="", refunded_at="", collected_at="", settled_at="")])], actor=actor)
    checked = validate_batch(batch.id)
    assert checked.status == "ready", checked.errors
    assert commit_batch(batch.id).status == "completed"
    order = Order.objects.get()
    assert order.created_at is None and order.confirmed_at is None and order.delivered_at is None
    assert order.lines.get().delivered_at is None and order.lines.get().returned_at is None
    assert order.shipments.get().dispatched_at is None
    assert order.returns.get().status == "inspected" and order.returns.get().inspected_at is None
    assert order.refunds.get().confirmed_at is None
    assert order.payments.get().collected_at is None
    assert order.payments.get().created_at is not None  # ingestion provenance, not invented collection time
    assert PaymentSettlement.objects.get().settled_at is None
    assert StockMovement.objects.count() == 0


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


def test_canonical_history_repeat_ignores_decimal_spelling_and_timezone_offsets(import_data, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    _, actor = import_data
    first = stage_upload(kind="history", source_name="canonical", files=[upload("history", [history_row()])], actor=actor)
    assert validate_batch(first.id).status == "ready"
    assert commit_batch(first.id).status == "completed"
    changed_spelling = history_row(unit_price="100.0", ordered_at="2026-01-01T06:00:00Z", delivered_at="2026-01-03T06:00:00+00:00",
                                   returned_at="2026-01-05T06:00:00Z", refunded_at="2026-01-06T06:00:00Z", collected_at="2026-01-03T06:00:00Z",
                                   settled_at="2026-01-04T06:00:00Z", collected_amount="200.0")
    second = stage_upload(kind="history", source_name="canonical", files=[upload("history", [changed_spelling])], actor=actor)
    assert validate_batch(second.id).status == "ready"
    assert commit_batch(second.id).result["skipped"] == 1
    assert Order.objects.count() == 1


def test_related_repeat_ignores_file_and_line_order(import_data, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    _, actor = import_data
    first = stage_upload(kind="history", source_name="reordered", files=related_files(), actor=actor)
    assert validate_batch(first.id).status == "ready"
    assert commit_batch(first.id).status == "completed"
    reversed_files = []
    for file in reversed(related_files()):
        reader = csv.DictReader(io.StringIO(file.read().decode()))
        rows = list(reader)
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=reader.fieldnames)
        writer.writeheader()
        writer.writerows(reversed(rows))
        reversed_files.append(SimpleUploadedFile(file.name, stream.getvalue().encode(), content_type="text/csv"))
    second = stage_upload(kind="history", source_name="reordered", files=reversed_files, actor=actor)
    checked = validate_batch(second.id)
    assert checked.status == "ready", checked.errors
    assert commit_batch(second.id).result["skipped"] == 2
    assert Order.objects.count() == 1


def test_changed_history_identity_fails_without_changing_existing_totals(import_data, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    sku, actor = import_data
    first = stage_upload(kind="history", source_name="conflicting", files=[upload("history", [history_row()])], actor=actor)
    assert validate_batch(first.id).status == "ready"
    assert commit_batch(first.id).status == "completed"
    original = Order.objects.get()
    fingerprint = original.import_fingerprint
    conflict = stage_upload(kind="history", source_name="conflicting", files=[upload("history", [history_row(unit_price="110.00")])], actor=actor)
    checked = validate_batch(conflict.id)
    assert checked.status == "failed"
    assert checked.errors[0]["code"] == "source_conflict"
    assert "conflicting data" in checked.errors[0]["message"]
    original.refresh_from_db()
    assert original.grand_total == 200 and original.import_fingerprint == fingerprint
    assert Order.objects.count() == Payment.objects.count() == PaymentSettlement.objects.count() == 1
    sku.refresh_from_db()
    assert sku.on_hand == 100


@pytest.mark.parametrize("kind", ["opening_stock", "adjustments"])
def test_stock_repeat_and_changed_identity_include_quantity_and_reason(import_data, settings, tmp_path, kind):
    settings.MEDIA_ROOT = tmp_path
    sku, actor = import_data
    if kind == "opening_stock":
        sku.on_hand = 0
        sku.save(update_fields=["on_hand"])
        row = {"source_record_id": "RECORD", "sku": sku.code, "quantity": "5"}
        changed = {**row, "quantity": "6"}
    else:
        row = {"source_record_id": "RECORD", "sku": sku.code, "quantity_delta": "5", "reason": "Verified physical count"}
        changed = {**row, "reason": "A different justification"}
    initial_stock = sku.on_hand
    for attempt in range(2):
        batch = stage_upload(kind=kind, source_name="stock-identity", files=[upload(kind, [row])], actor=actor)
        assert validate_batch(batch.id).status == "ready"
        result = commit_batch(batch.id)
        assert result.status == "completed"
        assert result.result["created" if attempt == 0 else "skipped"] == 1
    conflict = stage_upload(kind=kind, source_name="stock-identity", files=[upload(kind, [changed])], actor=actor)
    assert validate_batch(conflict.id).status == "failed"
    sku.refresh_from_db()
    assert sku.on_hand == initial_stock + 5
    assert StockMovement.objects.count() == 1


def test_stock_identity_cannot_silently_move_to_another_sku(import_data, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    sku, actor = import_data
    other = SKU.objects.create(product=sku.product, code="IMPORT-OTHER", price=25, on_hand=10)
    row = {"source_record_id": "SAME-ID", "sku": sku.code, "quantity_delta": "5", "reason": "Physical count"}
    first = stage_upload(kind="adjustments", source_name="identity-sku", files=[upload("adjustments", [row])], actor=actor)
    assert validate_batch(first.id).status == "ready"
    assert commit_batch(first.id).status == "completed"
    conflict = stage_upload(kind="adjustments", source_name="identity-sku", files=[upload("adjustments", [{**row, "sku": other.code}])], actor=actor)
    checked = validate_batch(conflict.id)
    assert checked.status == "failed" and checked.errors[0]["code"] == "source_conflict"
    other.refresh_from_db()
    assert other.on_hand == 10


def test_legacy_identity_without_fingerprint_is_unverifiable(import_data, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    _, actor = import_data
    first = correction_batch(actor, history_row(), source="unverifiable")
    assert commit_batch(first.id).status == "completed"
    Order.objects.update(import_fingerprint="")  # simulate records imported before canonical provenance existed
    repeated = correction_batch(actor, history_row(), source="unverifiable")
    repeated.refresh_from_db()
    assert repeated.status == "failed" and "unverifiable" in repeated.errors[0]["message"]
    assert Order.objects.count() == 1


def correction_batch(actor, row, source="reviewed"):
    batch = stage_upload(kind="history", source_name=source, files=[upload("history", [row])], actor=actor)
    validate_batch(batch.id)
    return batch


def test_reviewed_historical_revision_preserves_old_ledger_and_replaces_reporting(import_data, settings, tmp_path):
    from commerce.reporting import analytics, filters_from_params
    settings.MEDIA_ROOT = tmp_path
    sku, actor = import_data
    first = correction_batch(actor, history_row())
    assert commit_batch(first.id).status == "completed"
    old = Order.objects.get()
    old_payment_id = old.payments.get().id
    old_settlement_id = old.payments.get().settlements.get().id
    changed = correction_batch(actor, history_row(unit_price="150", collected_amount="300", settled_amount="300", refund_amount="150"))
    client = APIClient()
    client.force_authenticate(actor)
    preview = client.get(f"/api/v1/imports/{changed.id}/correction-preview/")
    assert preview.status_code == 200
    proposed = preview.json()
    assert proposed["can_correct"] and proposed["conflicts_count"] == 1
    assert proposed["orders"][0]["before"]["grand_total"] == "200.00"
    assert proposed["orders"][0]["after"]["grand_total"] == "300.00"
    approved = client.post(f"/api/v1/imports/{changed.id}/correct/", {"reason": "Administrator reconciled the corrected source export", "expected_revisions": proposed["expected_revisions"]}, format="json")
    assert approved.status_code == 202, approved.json()
    result = commit_batch(changed.id)
    assert result.status == "completed", result.errors
    assert result.result["revised"] == 1
    old.refresh_from_db()
    current = Order.objects.get(is_current=True)
    assert old.is_current is False and current.supersedes_id == old.id
    assert Payment.objects.get(pk=old_payment_id).amount == 200
    assert PaymentSettlement.objects.get(pk=old_settlement_id).amount == 200
    assert Order.objects.count() == PaymentSettlement.objects.count() == 2
    assert AuditEvent.objects.filter(event="historical_order_corrected").count() == 1
    report = analytics(filters_from_params({"start": "2026-01-01", "end": "2026-01-31"}))
    assert report["summary"]["orders"] == 1
    assert report["summary"]["ordered_value"] == "300.00"
    assert report["cash"]["collected_amount"] == "300.00"
    assert report["cash"]["settled_amount"] == "300.00"
    sku.refresh_from_db()
    assert sku.on_hand == 100 and sku.reserved == 0


def test_reviewed_revision_rechecks_stale_expected_identity_in_worker(import_data, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    _, actor = import_data
    assert commit_batch(correction_batch(actor, history_row()).id).status == "completed"
    first = correction_batch(actor, history_row(unit_price="110"))
    second = correction_batch(actor, history_row(unit_price="120"))
    client = APIClient()
    client.force_authenticate(actor)
    for batch in (first, second):
        preview = client.get(f"/api/v1/imports/{batch.id}/correction-preview/").json()
        assert client.post(f"/api/v1/imports/{batch.id}/correct/", {"reason": "Reviewed source correction for stale identity proof", "expected_revisions": preview["expected_revisions"]}, format="json").status_code == 202
    assert commit_batch(second.id).status == "completed"
    rejected = commit_batch(first.id)
    assert rejected.status == "failed" and "stale" in rejected.errors[0]["message"]
    assert Order.objects.count() == 2
    assert Order.objects.get(is_current=True).grand_total == 240


@pytest.mark.parametrize("role", ["customer", "operator", "analyst"])
def test_historical_correction_requires_administrator(import_data, settings, tmp_path, role):
    settings.MEDIA_ROOT = tmp_path
    _, actor = import_data
    batch = correction_batch(actor, history_row())
    user = get_user_model().objects.create_user(username="review-" + role, role=role, is_staff=True)
    client = APIClient()
    client.force_authenticate(user)
    assert client.get(f"/api/v1/imports/{batch.id}/correction-preview/").status_code == 403
    assert client.post(f"/api/v1/imports/{batch.id}/correct/", {"reason": "Cannot approve without administrator role", "expected_revisions": {}}, format="json").status_code == 403


def test_live_order_cannot_be_revised_as_history(import_data, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    _, actor = import_data
    Order.objects.create(number="LIVE", source="csv:reviewed", external_id="OLD-1", is_historical=False, customer_name="Synthetic", email="", phone="")
    batch = correction_batch(actor, history_row())
    client = APIClient()
    client.force_authenticate(actor)
    preview = client.get(f"/api/v1/imports/{batch.id}/correction-preview/")
    assert preview.status_code == 400 and "live orders" in str(preview.json())
    assert Order.objects.count() == 1 and Order.objects.get().is_current is True
