import csv
import io
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from commerce.models import AuditEvent, DeliveryZone, ImportBatch, Order, OrderLine, Payment, PaymentSettlement, Product, Refund, RefundLine, ReturnLine, ReturnRequest, Shipment, ShipmentLine
from commerce.models import SKU
from commerce.reporting import analytics, cash_activity, filters_from_params
from commerce.imports import SCHEMAS, commit_batch, stage_upload, validate_batch

TZ = ZoneInfo("Asia/Dhaka")


@pytest.fixture(autouse=True)
def isolated_reporting_cache(settings):
    # HTTP fixtures write directly to a rolled-back test database, outside API audits.
    # Never let their cache entries cross tests or leak into the live Redis instance.
    settings.CACHES = {**settings.CACHES, "reporting": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "reporting-test-" + uuid4().hex}}


def at(value):
    return datetime.fromisoformat(value).replace(tzinfo=TZ)


@pytest.fixture
def reference_data(db):
    product = Product.objects.create(name="Reference product", slug="reference", category="Testing")
    sku = SKU.objects.create(product=product, code="REF", price=100, on_hand=100)
    first = Order.objects.create(number="REF-1", customer_name="Private name", email="secret@example.invalid", phone="PRIVATE", created_at=at("2026-01-30T12:00:00"), source="csv:test")
    line = OrderLine.objects.create(order=first, sku=sku, sku_code=sku.code, product_name=product.name, quantity=3, unit_price=100,
                                    discount_total=30, shipped_quantity=3, delivered_quantity=3, returned_quantity=1,
                                    delivered_at=at("2026-02-02T12:00:00"), returned_at=at("2026-02-10T12:00:00"))
    for index, timestamp, quantity in [(1, "2026-01-31T12:00:00", 1), (2, "2026-02-02T12:00:00", 2)]:
        shipment = Shipment.objects.create(order=first, state="delivered", dispatched_at=first.created_at,
                                            delivered_at=at(timestamp), completed_at=at(timestamp))
        ShipmentLine.objects.create(shipment=shipment, order_line=line, quantity=quantity)
    returned = ReturnRequest.objects.create(order=first, status="inspected", reason="Test", inspected_at=at("2026-02-10T12:00:00"))
    ReturnLine.objects.create(return_request=returned, order_line=line, quantity=1, accepted_quantity=1)
    refund = Refund.objects.create(order=first, amount=90, status="confirmed", reason="Test", confirmed_at=at("2026-02-11T12:00:00"))
    RefundLine.objects.create(refund=refund, order_line=line, amount=90)
    second = Order.objects.create(number="REF-2", customer_name="Private name", email="secret@example.invalid", phone="PRIVATE", created_at=at("2026-01-05T12:00:00"))
    second_line = OrderLine.objects.create(order=second, sku=sku, sku_code=sku.code, product_name=product.name, quantity=2, unit_price=50,
                                           shipped_quantity=2, delivered_quantity=2, delivered_at=at("2026-01-06T12:00:00"))
    shipment = Shipment.objects.create(order=second, state="delivered", dispatched_at=second.created_at,
                                        delivered_at=second_line.delivered_at, completed_at=second_line.delivered_at)
    ShipmentLine.objects.create(shipment=shipment, order_line=second_line, quantity=2)
    payment = Payment.objects.create(order=second, method="cod", status="successful", amount=110,
                           collected_at=at("2026-01-06T12:00:00"), settled_amount=110, settled_at=at("2026-01-07T12:00:00"))
    PaymentSettlement.objects.create(payment=payment, amount=110, settled_at=payment.settled_at, reference="reference-settlement", source="demo")
    return product


def test_activity_and_delivery_cohort_are_distinct(reference_data):
    january = analytics(filters_from_params({"start": "2026-01-01", "end": "2026-01-31"}))
    assert january["summary"] == {"orders": 2, "ordered_units": 5, "ordered_value": "370.00", "delivered_units": 3,
                                  "delivered_value": "190.00", "returned_units": 0, "refunded_amount": "0.00", "net_delivered_value": "190.00"}
    # February's accepted return belongs to the first January delivery under documented FIFO allocation.
    assert january["cohort"]["delivered_units"] == 3
    assert january["cohort"]["returned_units"] == 1
    assert january["cohort"]["return_rate"] == 33.33
    assert january["delivery"]["delivered_shipments"] == 2
    assert january["cash"]["cod_collected_amount"] == "110.00"
    assert january["cash"]["settled_amount"] == "110.00"
    february = analytics(filters_from_params({"start": "2026-02-01", "end": "2026-02-28"}))
    assert february["summary"]["delivered_value"] == "180.00"
    assert february["summary"]["returned_units"] == 1
    assert february["summary"]["refunded_amount"] == "90.00"
    assert february["summary"]["net_delivered_value"] == "90.00"
    assert february["cohort"]["returned_units"] == 0


def test_drilldown_and_csv_reconcile_without_customer_data(reference_data):
    analyst = get_user_model().objects.create_user(username="analyst-test", password="test-password", role="analyst", is_staff=True)
    client = APIClient()
    client.force_authenticate(analyst)
    query = "metric=delivered_units&start=2026-01-01&end=2026-01-31"
    response = client.get("/api/v1/analytics/drilldown/?" + query)
    assert response.status_code == 200
    rows = response.json()["results"]
    assert sum(row["quantity"] for row in rows) == 3
    assert sum(Decimal(row["value"]) for row in rows) == Decimal("190")
    exported = client.get("/api/v1/analytics/export/?" + query)
    csv_rows = list(csv.DictReader(io.StringIO(exported.content.decode())))
    assert [row["id"] for row in csv_rows] == [row["id"] for row in rows]
    assert "secret@example.invalid" not in exported.content.decode()
    assert "PRIVATE" not in exported.content.decode()
    assert client.get("/api/v1/analytics/?start=bad").status_code == 400


def test_customer_cannot_access_reporting(reference_data):
    customer = get_user_model().objects.create_user(username="customer-test", password="test-password")
    client = APIClient()
    client.force_authenticate(customer)
    assert client.get("/api/v1/analytics/").status_code == 403


@pytest.mark.parametrize("role,is_staff,expected", [("customer", True, 403), ("analyst", False, 200), ("operator", False, 200), ("administrator", False, 200)])
def test_reporting_uses_company_role_not_django_admin_flag(reference_data, role, is_staff, expected):
    user = get_user_model().objects.create_user(username=f"role-{role}", role=role, is_staff=is_staff)
    client = APIClient()
    client.force_authenticate(user)
    assert client.get("/api/v1/analytics/?start=2026-01-01&end=2026-01-31").status_code == expected


def test_tax_and_shipping_refund_allocations_are_excluded_from_merchandise(reference_data):
    refund_line = RefundLine.objects.first()
    refund_line.amount = Decimal("109.00")
    refund_line.tax_amount = Decimal("9.00")
    refund_line.shipping_amount = Decimal("10.00")
    refund_line.save()
    result = analytics(filters_from_params({"start": "2026-02-01", "end": "2026-02-28", "product_ids": str(reference_data.id)}))
    assert result["summary"]["refunded_amount"] == "90.00"
    assert result["summary"]["net_delivered_value"] == "90.00"
    assert result["cash"]["product_filter_applied"] is False


def test_verified_exception_receipts_are_visible_separately(reference_data):
    Payment.objects.create(order=Order.objects.first(), method="sslcommerz", status="exception", amount=25,
                           is_sandbox=True, collected_at=at("2026-01-08T12:00:00"))
    result = analytics(filters_from_params({"start": "2026-01-01", "end": "2026-01-31"}))
    assert result["cash"]["collected_amount"] == "135.00"
    assert result["cash"]["exception_collected_amount"] == "25.00"
    assert result["cash"]["sandbox_collected_amount"] == "25.00"
    assert result["cash"]["settled_amount"] == "110.00"


def test_partial_settlements_keep_each_transfer_in_its_actual_period(reference_data):
    order = Order.objects.create(number="PARTIAL-CASH", customer_name="Synthetic", email="", phone="", created_at=at("2026-01-01T12:00:00"))
    payment = Payment.objects.create(order=order, method="cod", status="successful", amount=100,
                                     collected_at=at("2026-01-02T12:00:00"), settled_amount=100, settled_at=at("2026-01-09T12:00:00"))
    PaymentSettlement.objects.create(payment=payment, amount=40, settled_at=at("2026-01-08T12:00:00"), reference="TRANSFER-1", source="live")
    PaymentSettlement.objects.create(payment=payment, amount=60, settled_at=at("2026-01-09T12:00:00"), reference="TRANSFER-2", source="live")
    first_day = cash_activity(filters_from_params({"start": "2026-01-08", "end": "2026-01-08"}))
    second_day = cash_activity(filters_from_params({"start": "2026-01-09", "end": "2026-01-09"}))
    both_days = cash_activity(filters_from_params({"start": "2026-01-08", "end": "2026-01-09"}))
    assert first_day["settled_amount"] == "40.00"
    assert second_day["settled_amount"] == "60.00"
    assert both_days["settled_amount"] == "100.00"


@pytest.mark.django_db
def test_fresh_demo_seed_creates_settlement_events_and_repeat_does_not_duplicate(settings):
    from django.core.management import call_command
    from django.db.models import Sum
    settings.DEBUG = True
    settings.PRODUCTSTAT_DEMO = True
    output = io.StringIO()
    call_command("seed_demo", orders=20, skus=5, as_of="2026-11-15", stdout=output)
    count = PaymentSettlement.objects.count()
    assert count > 0
    assert set(PaymentSettlement.objects.values_list("source", flat=True)) == {"demo"}
    assert PaymentSettlement.objects.aggregate(total=Sum("amount"))["total"] == Payment.objects.aggregate(total=Sum("settled_amount"))["total"]
    call_command("seed_demo", orders=20, skus=5, as_of="2026-11-15", stdout=output)
    assert PaymentSettlement.objects.count() == count


def staff_client():
    user = get_user_model().objects.create_user(username="cache-admin", role="administrator")
    client = APIClient()
    client.force_authenticate(user)
    return client, user


def test_http_overview_reuses_canonical_filters_and_keeps_visible_generation_time(reference_data):
    client, _ = staff_client()
    base = "/api/v1/analytics/?start=2026-01-01&end=2026-01-31&product_ids="
    with patch("commerce.reporting_views.analytics", wraps=analytics) as calculate:
        first = client.get(base + f"{reference_data.id},{reference_data.id}")
        second = client.get(base + str(reference_data.id))
        assert first.status_code == second.status_code == 200
        assert first["X-Analytics-Cache"] == "MISS"
        assert second["X-Analytics-Cache"] == "HIT"
        assert second["Cache-Control"] == "private, no-store"
        assert first.json() == second.json()
        assert calculate.call_count == 1


def test_older_audit_timestamp_committed_later_still_invalidates(reference_data):
    client, _ = staff_client()
    AuditEvent.objects.create(event="newer", entity="test", reference="1")
    url = "/api/v1/analytics/?start=2026-01-01&end=2026-01-31"
    assert client.get(url)["X-Analytics-Cache"] == "MISS"
    assert client.get(url)["X-Analytics-Cache"] == "HIT"
    late = AuditEvent.objects.create(event="older-transaction-committed-later", entity="test", reference="2")
    AuditEvent.objects.filter(pk=late.pk).update(created_at=timezone.now() - timedelta(days=1))
    # MAX(created_at) is unchanged. The committed append count must change the key.
    assert client.get(url)["X-Analytics-Cache"] == "MISS"


def test_committed_history_import_refreshes_cached_totals(reference_data, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    client, actor = staff_client()
    url = "/api/v1/analytics/?start=2026-01-01&end=2026-01-31"
    assert client.get(url).json()["summary"]["ordered_value"] == "370.00"
    assert client.get(url)["X-Analytics-Cache"] == "HIT"
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=SCHEMAS["history"])
    writer.writeheader()
    writer.writerow({"source_order_id": "CACHE-IMPORT", "source_line_id": "1", "sku": "REF", "ordered_at": "2026-01-10T12:00:00+06:00",
                     "status": "delivered", "payment_method": "cod", "quantity": "1", "unit_price": "100", "shipped_quantity": "1", "delivered_quantity": "1",
                     "delivered_at": "2026-01-11T12:00:00+06:00", "collected_amount": "100", "collected_at": "2026-01-11T12:00:00+06:00"})
    upload = SimpleUploadedFile("history.csv", stream.getvalue().encode(), content_type="text/csv")
    batch = stage_upload(kind="history", source_name="cache-proof", files=[upload], actor=actor)
    assert validate_batch(batch.id).status == "ready"
    assert commit_batch(batch.id).status == "completed"
    response = client.get(url)
    assert response["X-Analytics-Cache"] == "MISS"
    assert response.json()["summary"]["ordered_value"] == "470.00"
    assert response.json()["summary"]["orders"] == 3


def test_import_commit_revision_is_independent_of_audit_timestamp(reference_data):
    client, _ = staff_client()
    url = "/api/v1/analytics/?start=2026-01-01&end=2026-01-31"
    assert client.get(url)["X-Analytics-Cache"] == "MISS"
    ImportBatch.objects.create(kind="history", status="completed", file="unused-reference.csv", filename="reference.csv",
                               source_name="revision-proof", committed_at=timezone.now() - timedelta(days=10))
    assert client.get(url)["X-Analytics-Cache"] == "MISS"


def test_redis_failure_falls_back_to_fresh_database_report(reference_data):
    client, _ = staff_client()
    class UnavailableCache:
        def get(self, key):
            raise ConnectionError("cache unavailable")
    with patch("commerce.reporting_cache.get_cache", return_value=UnavailableCache()):
        response = client.get("/api/v1/analytics/?start=2026-01-01&end=2026-01-31")
    assert response.status_code == 200
    assert response["X-Analytics-Cache"] == "BYPASS"
    assert response.json()["summary"]["ordered_value"] == "370.00"


def test_purchase_delivery_return_and_refund_immediately_refresh_http_cache(reference_data, settings):
    settings.PRODUCTSTAT_DEMO = True
    client, _ = staff_client()
    sku = reference_data.skus.get()
    zone = DeliveryZone.objects.create(name="Cache test zone", charge=0)
    url = "/api/v1/analytics/"
    assert client.get(url).json()["summary"]["orders"] == 0
    assert client.get(url)["X-Analytics-Cache"] == "HIT"
    assert client.post("/api/v1/cart/", {"sku_id": str(sku.id), "quantity": 1}, format="json").status_code == 200
    checkout = client.post("/api/v1/checkout/", {"customer_name": "Cache Customer", "email": "", "phone": "01712345678",
                                               "address": {"line1": "21 Synthetic Road", "city": "Chattogram"},
                                               "delivery_zone_id": zone.id, "payment_method": "cod"},
                           format="json", HTTP_IDEMPOTENCY_KEY=uuid4().hex)
    assert checkout.status_code == 201, checkout.json()
    order = checkout.json()["order"]
    after_purchase = client.get(url)
    assert after_purchase["X-Analytics-Cache"] == "MISS"
    assert after_purchase.json()["summary"]["ordered_units"] == 1
    for action in ("dispatch", "deliver"):
        assert client.post(f"/api/v1/staff/orders/{order['id']}/action/", {"action": action, "carrier": "Test", "tracking_number": "CACHE"}, format="json").status_code == 200
    assert client.get(url).json()["summary"]["delivered_units"] == 1
    assert client.post(f"/api/v1/staff/orders/{order['id']}/action/", {"action": "collect_cod", "amount": "100.00", "reference": "CACHE-RECEIPT"}, format="json").status_code == 200
    assert client.post(f"/api/v1/staff/orders/{order['id']}/action/", {"action": "settle_cod", "amount": "40.00", "reference": "CACHE-SETTLE-1"}, format="json").status_code == 200
    first_settlement = client.get(url)
    assert first_settlement["X-Analytics-Cache"] == "MISS"
    assert first_settlement.json()["cash"]["settled_amount"] == "40.00"
    assert client.get(url)["X-Analytics-Cache"] == "HIT"
    assert client.post(f"/api/v1/staff/orders/{order['id']}/action/", {"action": "settle_cod", "amount": "60.00", "reference": "CACHE-SETTLE-2"}, format="json").status_code == 200
    second_settlement = client.get(url)
    assert second_settlement["X-Analytics-Cache"] == "MISS"
    assert second_settlement.json()["cash"]["settled_amount"] == "100.00"
    requested = client.post(f"/api/v1/orders/{order['id']}/returns/", {"reason": "Synthetic verification", "lines": [{"order_line_id": order['lines'][0]['id'], "quantity": 1}]}, format="json")
    assert requested.status_code == 201, requested.json()
    returned = requested.json()
    for action in ("approve", "receive"):
        assert client.post(f"/api/v1/staff/returns/{returned['id']}/action/", {"action": action}, format="json").status_code == 200
    assert client.post(f"/api/v1/staff/returns/{returned['id']}/action/", {"action": "inspect", "lines": [{"id": returned['lines'][0]['id'], "accepted_quantity": 1, "restock_quantity": 0, "disposition": "quarantine"}]}, format="json").status_code == 200
    after_return = client.get(url)
    assert after_return["X-Analytics-Cache"] == "MISS"
    assert after_return.json()["summary"]["returned_units"] == 1
    refund = Refund.objects.filter(order_id=order["id"]).get()
    assert client.post(f"/api/v1/staff/refunds/{refund.id}/confirm/", {"reference": "CACHE-REFUND"}, format="json").status_code == 200
    after_refund = client.get(url)
    assert after_refund["X-Analytics-Cache"] == "MISS"
    assert after_refund.json()["summary"]["refunded_amount"] == "100.00"
