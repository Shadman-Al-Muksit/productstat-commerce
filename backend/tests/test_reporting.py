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

from commerce.models import AuditEvent, DeliveryZone, ImportBatch, Order, OrderLine, Payment, PaymentSettlement, Product, Refund, RefundLine, ReturnLine, ReturnRequest, Shipment, ShipmentLine, StockMovement
from commerce.models import SKU
from commerce.reporting import analytics, cash_activity, delivery_cohort, filters_from_params
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
    assert january["summary"] == {"orders": 2, "ordered_units": 5, "cancelled_units": 0, "ordered_value": "370.00", "delivered_units": 3,
                                  "delivered_value": "190.00", "returned_units": 0, "returned_value": "0.00", "refunded_amount": "0.00", "net_delivered_value": "190.00"}
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
    refund_line.refund.amount = Decimal("109.00")
    refund_line.refund.save(update_fields=["amount"])
    result = analytics(filters_from_params({"start": "2026-02-01", "end": "2026-02-28", "product_ids": str(reference_data.id)}))
    assert result["summary"]["refunded_amount"] == "90.00"
    assert result["summary"]["net_delivered_value"] == "90.00"
    assert result["cash"]["refunded_amount"] == "109.00"
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


def test_variant_activity_reconciles_with_product_and_includes_zero_activity(reference_data):
    first_sku = reference_data.skus.get()
    first_sku.code = "REF-RENAMED"
    first_sku.save(update_fields=["code"])
    second_sku = SKU.objects.create(product=reference_data, code="REF-SECOND", label="Second variant", price=50, on_hand=10)
    idle = SKU.objects.create(product=reference_data, code="REF-IDLE", label="Archived variant", price=75, is_active=False)
    order = Order.objects.create(number="VARIANT-ORDER", customer_name="Private variant buyer", email="variant-secret@example.invalid", phone="PRIVATE", created_at=at("2026-02-01T12:00:00"))
    line = OrderLine.objects.create(order=order, sku=second_sku, sku_code=second_sku.code, product_name=reference_data.name,
                                    quantity=2, shipped_quantity=2, delivered_quantity=2, returned_quantity=1, unit_price=50,
                                    delivered_at=at("2026-02-02T12:00:00"), returned_at=at("2026-02-12T12:00:00"))
    shipment = Shipment.objects.create(order=order, state="delivered", dispatched_at=order.created_at, delivered_at=line.delivered_at, completed_at=line.delivered_at)
    ShipmentLine.objects.create(shipment=shipment, order_line=line, quantity=2)
    returned = ReturnRequest.objects.create(order=order, status="inspected", reason="Partial return", inspected_at=line.returned_at)
    ReturnLine.objects.create(return_request=returned, order_line=line, quantity=1, accepted_quantity=1)
    refund = Refund.objects.create(order=order, amount=50, status="confirmed", reason="Partial", confirmed_at=at("2026-02-13T12:00:00"))
    RefundLine.objects.create(refund=refund, order_line=line, amount=50)
    client, _ = staff_client()
    response = client.get(f"/api/v1/analytics/variants/?product_id={reference_data.id}&start=2026-02-01&end=2026-02-28")
    assert response.status_code == 200
    payload = response.json()
    variants = {row["sku_id"]: row for row in payload["results"]}
    assert len(variants) == 3
    assert variants[str(first_sku.id)]["code"] == "REF-RENAMED"
    assert variants[str(first_sku.id)]["delivered_units"] == 2
    assert variants[str(idle.id)]["is_active"] is False
    for metric in ("ordered_units", "cancelled_units", "delivered_units", "returned_units"):
        assert variants[str(idle.id)][metric] == 0
    for metric in ("delivered_value", "returned_value", "refunded_amount", "net_delivered_value"):
        assert variants[str(idle.id)][metric] == "0.00"
    product = analytics(filters_from_params({"start": "2026-02-01", "end": "2026-02-28", "product_ids": str(reference_data.id)}))["summary"]
    for metric in ("ordered_units", "cancelled_units", "delivered_units", "returned_units", "delivered_value", "returned_value", "refunded_amount", "net_delivered_value"):
        assert sum(Decimal(str(row[metric])) for row in variants.values()) == Decimal(str(product[metric]))
    assert payload["filters"]["product_id"] == str(reference_data.id)
    assert "variant-secret@example.invalid" not in response.content.decode()
    assert "Private variant buyer" not in response.content.decode()


def test_variant_endpoint_requires_one_product_and_company_role(reference_data):
    client, _ = staff_client()
    assert client.get("/api/v1/analytics/variants/").status_code == 400
    assert client.get("/api/v1/analytics/variants/?product_id=bad").status_code == 400
    assert client.get(f"/api/v1/analytics/variants/?product_id={reference_data.id},{reference_data.id}").status_code == 400
    assert client.get(f"/api/v1/analytics/variants/?product_id={uuid4()}").status_code == 404
    assert client.get(f"/api/v1/analytics/variants/?product_id={reference_data.id}&start=bad").status_code == 400
    customer = get_user_model().objects.create_user(username="variant-customer", role="customer", is_staff=True)
    client.force_authenticate(customer)
    assert client.get(f"/api/v1/analytics/variants/?product_id={reference_data.id}").status_code == 403
    analyst = get_user_model().objects.create_user(username="variant-analyst", role="analyst")
    client.force_authenticate(analyst)
    assert client.get(f"/api/v1/analytics/variants/?product_id={reference_data.id}").status_code == 200


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
    assert after_return.json()["summary"]["returned_value"] == "100.00"
    assert after_return.json()["summary"]["refunded_amount"] == "0.00"
    assert after_return.json()["summary"]["net_delivered_value"] == "0.00"
    refund = Refund.objects.filter(order_id=order["id"]).get()
    assert client.post(f"/api/v1/staff/refunds/{refund.id}/confirm/", {"reference": "CACHE-REFUND"}, format="json").status_code == 200
    after_refund = client.get(url)
    assert after_refund["X-Analytics-Cache"] == "MISS"
    assert after_refund.json()["summary"]["refunded_amount"] == "100.00"
    assert after_refund.json()["summary"]["net_delivered_value"] == "0.00"


def test_accepted_return_reduces_net_on_inspection_not_later_refund(reference_data):
    refund = Refund.objects.first()
    refund.status = "pending"
    refund.save(update_fields=["status"])
    inspection = analytics(filters_from_params({"start": "2026-02-10", "end": "2026-02-10"}))
    assert inspection["summary"]["delivered_value"] == "0.00"
    assert inspection["summary"]["returned_value"] == "90.00"
    assert inspection["summary"]["refunded_amount"] == "0.00"
    assert inspection["summary"]["net_delivered_value"] == "-90.00"
    assert inspection["trend"][0]["net_delivered_value"] == "-90.00"
    assert inspection["products"][0]["returned_value"] == "90.00"
    refund.status = "confirmed"
    refund.save(update_fields=["status"])
    payout = analytics(filters_from_params({"start": "2026-02-11", "end": "2026-02-11"}))
    assert payout["summary"]["returned_value"] == "0.00"
    assert payout["summary"]["refunded_amount"] == "90.00"
    assert payout["summary"]["net_delivered_value"] == "0.00"


def test_mature_delivery_cohort_remains_preliminary_for_linked_unresolved_cases(reference_data):
    line = OrderLine.objects.filter(sku__product=reference_data).order_by("-order__number").first()
    pending = ReturnRequest.objects.create(order=line.order, status="requested", reason="Still awaiting resolution")
    ReturnRequest.objects.filter(pk=pending.pk).update(created_at=at("2026-01-07T12:00:00"))
    ReturnLine.objects.create(return_request=pending, order_line=line, quantity=1)
    other_product = Product.objects.create(name="Unrelated", slug="unrelated", category="Other")
    other_sku = SKU.objects.create(product=other_product, code="OTHER", price=10)
    other_order = Order.objects.create(number="UNRELATED", customer_name="Synthetic", email="", phone="", created_at=at("2026-01-01T12:00:00"))
    other_line = OrderLine.objects.create(order=other_order, sku=other_sku, sku_code="OTHER", product_name="Unrelated", quantity=1, shipped_quantity=1,
                                         delivered_quantity=1, unit_price=10, delivered_at=at("2026-01-02T12:00:00"))
    other_case = ReturnRequest.objects.create(order=other_order, status="requested", reason="Other product")
    ReturnLine.objects.create(return_request=other_case, order_line=other_line, quantity=1)
    filters = filters_from_params({"start": "2026-01-01", "end": "2026-01-31", "product_ids": str(reference_data.id)})
    for status in ("requested", "approved", "received"):
        pending.status = status
        pending.save(update_fields=["status"])
        cohort = analytics(filters)["cohort"]
        assert cohort["open_window_units"] == 0
        assert cohort["unresolved_cases"] == 1
        assert cohort["preliminary"] is True
    pending.status = "rejected"
    pending.save(update_fields=["status"])
    cohort = analytics(filters)["cohort"]
    assert cohort["unresolved_cases"] == 0
    assert cohort["preliminary"] is False


def test_cancellation_activity_uses_each_actual_release_date_and_drilldown(reference_data, settings):
    from commerce import services
    settings.PRODUCTSTAT_DEMO = True
    client, actor = staff_client()
    sku = reference_data.skus.get()
    zone = DeliveryZone.objects.create(name="Cancellation zone", charge=0)
    payload = {"customer_name": "Synthetic", "email": "", "phone": "01712345678", "address": {"line1": "Test", "city": "Chattogram"}, "delivery_zone_id": zone.id, "payment_method": "cod"}
    with patch("commerce.services.timezone.now", return_value=at("2026-01-01T12:00:00")):
        order, _ = services.checkout({str(sku.id): 3}, payload, "dated-cancellations", "fixture-session")
    line = order.lines.get()
    with patch("commerce.services.timezone.now", return_value=at("2026-01-05T12:00:00")):
        services.cancel_order(order.id, actor, [{"order_line_id": str(line.id), "quantity": 1}])
    with patch("commerce.services.timezone.now", return_value=at("2026-01-09T12:00:00")):
        services.cancel_order(order.id, actor)
    first = analytics(filters_from_params({"start": "2026-01-05", "end": "2026-01-05"}))
    second = analytics(filters_from_params({"start": "2026-01-09", "end": "2026-01-09"}))
    assert first["summary"]["cancelled_units"] == 1
    assert second["summary"]["cancelled_units"] == 2
    assert first["trend"][0]["cancelled_units"] == 1
    assert first["products"][0]["cancelled_units"] == 1
    url = "/api/v1/analytics/drilldown/?metric=cancelled_units&start=2026-01-05&end=2026-01-05"
    detail = client.get(url)
    assert detail.status_code == 200
    row = detail.json()["results"][0]
    assert row["order_number"] == order.number
    assert row["quantity"] == 1
    assert row["value"] == "100.00"
    exported = client.get(url.replace("drilldown/", "export/"))
    csv_rows = list(csv.DictReader(io.StringIO(exported.content.decode())))
    assert csv_rows[0]["id"] == row["id"]
    assert csv_rows[0]["quantity"] == "1"
    # A legacy cumulative cancellation snapshot without observed release events has no date invented.
    undated = Order.objects.create(number="UNDATED-CANCEL", customer_name="Synthetic", email="", phone="", status="cancelled", is_historical=True, created_at=at("2026-01-09T12:00:00"))
    OrderLine.objects.create(order=undated, sku=sku, sku_code=sku.code, product_name=reference_data.name, quantity=2, cancelled_quantity=2, unit_price=100)
    assert analytics(filters_from_params({"start": "2026-01-09", "end": "2026-01-09"}))["summary"]["cancelled_units"] == 2


def test_return_reasons_count_multi_line_case_once_and_apply_product_filters(reference_data):
    sku = reference_data.skus.get()
    second = SKU.objects.create(product=reference_data, code="REASON-SECOND", price=40)
    other = Product.objects.create(name="Other reason product", slug="other-reason", category="Other")
    other_sku = SKU.objects.create(product=other, code="REASON-OTHER", price=50)
    order = Order.objects.create(number="REASON-ORDER", customer_name="Synthetic", email="", phone="", created_at=at("2026-02-01T12:00:00"))
    shipment = Shipment.objects.create(order=order, state="delivered", dispatched_at=order.created_at, delivered_at=at("2026-02-02T12:00:00"))
    returned = ReturnRequest.objects.create(order=order, status="inspected", reason="Fit", inspected_at=at("2026-02-12T12:00:00"))
    for current_sku, quantity in ((sku, 1), (second, 2), (other_sku, 3)):
        line = OrderLine.objects.create(order=order, sku=current_sku, sku_code=current_sku.code, product_name=current_sku.product.name, quantity=quantity,
                                        unit_price=current_sku.price, shipped_quantity=quantity, delivered_quantity=quantity, returned_quantity=quantity,
                                        delivered_at=shipment.delivered_at, returned_at=returned.inspected_at)
        ShipmentLine.objects.create(shipment=shipment, order_line=line, quantity=quantity)
        ReturnLine.objects.create(return_request=returned, order_line=line, quantity=quantity, accepted_quantity=quantity)
    declined = ReturnRequest.objects.create(order=order, status="rejected", reason="Rejected", inspected_at=at("2026-02-12T12:00:00"))
    ReturnLine.objects.create(return_request=declined, order_line=order.lines.first(), quantity=1, accepted_quantity=1)
    zero = ReturnRequest.objects.create(order=order, status="inspected", reason="Unaccepted", inspected_at=at("2026-02-12T12:00:00"))
    ReturnLine.objects.create(return_request=zero, order_line=order.lines.first(), quantity=1, accepted_quantity=0)
    all_products = analytics(filters_from_params({"start": "2026-02-01", "end": "2026-02-28"}))
    assert next(row for row in all_products["return_reasons"] if row["reason"] == "Fit") == {"reason": "Fit", "units": 6, "count": 1}
    selected = analytics(filters_from_params({"start": "2026-02-01", "end": "2026-02-28", "product_ids": str(reference_data.id)}))
    assert next(row for row in selected["return_reasons"] if row["reason"] == "Fit") == {"reason": "Fit", "units": 3, "count": 1}
    assert not any(row["reason"] in {"Rejected", "Unaccepted"} for row in selected["return_reasons"])
    assert sum(row["units"] for row in selected["return_reasons"]) == selected["summary"]["returned_units"]


def test_unknown_dates_remain_outside_intervals_with_explicit_all_record_coverage(reference_data):
    sku = reference_data.skus.get()
    unknown = Order.objects.create(number="UNKNOWN-DATES", customer_name="Synthetic", email="", phone="", source="csv:coverage", is_historical=True,
                                    created_at=None, subtotal=400, grand_total=400)
    line = OrderLine.objects.create(order=unknown, sku=sku, sku_code=sku.code, product_name=reference_data.name, quantity=4,
                                    shipped_quantity=3, delivered_quantity=3, returned_quantity=1, cancelled_quantity=1, unit_price=100)
    shipment = Shipment.objects.create(order=unknown, state="delivered", dispatched_at=None)
    ShipmentLine.objects.create(shipment=shipment, order_line=line, quantity=3)
    returned = ReturnRequest.objects.create(order=unknown, status="inspected", reason="Undated")
    ReturnLine.objects.create(return_request=returned, order_line=line, quantity=1, accepted_quantity=1)
    payment = Payment.objects.create(order=unknown, method="cod", status="successful", amount=300, settled_amount=50)
    PaymentSettlement.objects.create(payment=payment, amount=50, settled_at=None, reference="unknown-transfer", source="import")
    known = Order.objects.create(number="KNOWN-EVENTS", customer_name="Synthetic", email="", phone="", source="csv:coverage", is_historical=True,
                                 created_at=at("2026-01-01T12:00:00"))
    known_line = OrderLine.objects.create(order=known, sku=sku, sku_code=sku.code, product_name=reference_data.name, quantity=2,
                                          shipped_quantity=2, delivered_quantity=2, returned_quantity=1, unit_price=100)
    observed = Shipment.objects.create(order=known, state="delivered", dispatched_at=None, delivered_at=at("2026-01-03T12:00:00"))
    ShipmentLine.objects.create(shipment=observed, order_line=known_line, quantity=2)
    observed_return = ReturnRequest.objects.create(order=known, status="inspected", reason="Known event", inspected_at=at("2026-01-04T12:00:00"))
    ReturnLine.objects.create(return_request=observed_return, order_line=known_line, quantity=1, accepted_quantity=1)
    result = analytics(filters_from_params({"start": "2030-01-01", "end": "2030-01-31", "product_ids": str(reference_data.id)}))
    assert result["summary"]["orders"] == result["summary"]["delivered_units"] == result["summary"]["returned_units"] == 0
    assert result["cash"]["collected_amount"] == result["cash"]["settled_amount"] == "0.00"
    assert result["coverage"] == {"missing_order_date_units": 4, "missing_delivery_date_units": 3, "missing_return_date_units": 1,
                                   "cancelled_units_without_dated_event": 1, "undated_collection_amount": "300.00", "undated_settlement_amount": "50.00",
                                   "basis": "All matching current history, not the selected interval; unknown dates are excluded from dated metrics. Unit counts follow product filters; monetary coverage is company-wide."}
    unknown.refresh_from_db()
    assert unknown.created_at is None
    shipment.refresh_from_db()
    assert shipment.dispatched_at is None


def test_superseded_history_is_excluded_from_every_report_without_deleting_evidence(reference_data):
    old = Order.objects.get(number="REF-1")
    old.external_id = "REVISION-1"
    old.is_historical = True
    old.is_current = False
    old.save(update_fields=["external_id", "is_historical", "is_current"])
    old_payment = Payment.objects.create(order=old, method="cod", status="successful", amount=270, collected_at=at("2026-02-02T12:00:00"), settled_amount=100, settled_at=at("2026-02-03T12:00:00"))
    PaymentSettlement.objects.create(payment=old_payment, amount=100, settled_at=old_payment.settled_at, reference="old-transfer", source="legacy_aggregate")
    sku = reference_data.skus.get()
    old_release = StockMovement.objects.create(sku=sku, reserved_delta=-1, kind="cancel", reference=str(old.id))
    StockMovement.objects.filter(pk=old_release.pk).update(created_at=at("2026-02-05T12:00:00"))
    current = Order.objects.create(number="REF-1-CORRECTED", source=old.source, external_id=old.external_id, supersedes=old,
                                   is_historical=True, customer_name="Synthetic", email="", phone="", created_at=old.created_at)
    line = OrderLine.objects.create(order=current, sku=sku, sku_code=sku.code, product_name=reference_data.name, quantity=1, unit_price=50,
                                    shipped_quantity=1, delivered_quantity=1, delivered_at=at("2026-02-02T12:00:00"))
    delivered = Shipment.objects.create(order=current, state="delivered", dispatched_at=None, delivered_at=line.delivered_at)
    ShipmentLine.objects.create(shipment=delivered, order_line=line, quantity=1)
    paid = Payment.objects.create(order=current, method="cod", status="successful", amount=50, collected_at=line.delivered_at, settled_amount=20, settled_at=at("2026-02-03T12:00:00"))
    PaymentSettlement.objects.create(payment=paid, amount=20, settled_at=paid.settled_at, reference="current-transfer", source="import")
    refund = Refund.objects.create(order=current, amount=10, status="confirmed", reason="Price adjustment", confirmed_at=at("2026-02-11T12:00:00"))
    RefundLine.objects.create(refund=refund, order_line=line, amount=10)
    result = analytics(filters_from_params({"start": "2026-02-01", "end": "2026-02-28", "product_ids": str(reference_data.id)}))
    assert result["summary"]["delivered_units"] == 1
    assert result["summary"]["delivered_value"] == result["summary"]["net_delivered_value"] == "50.00"
    assert result["summary"]["returned_units"] == result["summary"]["cancelled_units"] == 0
    assert result["summary"]["refunded_amount"] == result["cash"]["refunded_amount"] == "10.00"
    assert result["cash"]["collected_amount"] == "50.00"
    assert result["cash"]["settled_amount"] == "20.00"
    assert result["delivery"]["delivered_shipments"] == result["cohort"]["delivered_units"] == 1
    assert result["return_reasons"] == []
    client, _ = staff_client()
    rows = client.get("/api/v1/analytics/drilldown/?metric=delivered_units&start=2026-02-01&end=2026-02-28").json()["results"]
    assert [row["order_number"] for row in rows] == [current.number]
    assert Order.objects.filter(pk=old.id).exists()
    assert old.lines.count() == 1 and old.refunds.count() == 1 and old.payments.count() == 1


@pytest.mark.django_db
def test_delivery_cohort_uses_inclusive_dhaka_calendar_day_window():
    product = Product.objects.create(name="Calendar window", slug="calendar-window", category="Test")
    sku = SKU.objects.create(product=product, code="CALENDAR", price=100)
    for index, delivered_at in enumerate(("2026-01-02T23:59:00", "2026-01-03T00:00:00", "2026-01-03T08:00:00")):
        order = Order.objects.create(number=f"CALENDAR-{index}", customer_name="Synthetic", email="", phone="", created_at=at("2026-01-01T00:00:00"))
        line = OrderLine.objects.create(order=order, sku=sku, sku_code=sku.code, product_name=product.name, quantity=1, unit_price=100,
                                        shipped_quantity=1, delivered_quantity=1, delivered_at=at(delivered_at))
        shipment = Shipment.objects.create(order=order, state="delivered", dispatched_at=None, delivered_at=line.delivered_at)
        ShipmentLine.objects.create(shipment=shipment, order_line=line, quantity=1)
    filters = filters_from_params({"start": "2026-01-01", "end": "2026-01-10", "product_ids": str(product.id)})
    with patch("commerce.reporting.timezone.now", return_value=at("2026-01-10T23:00:00")):
        final_day = delivery_cohort(filters)
    assert final_day["open_window_units"] == 2
    assert final_day["preliminary"] is True
    with patch("commerce.reporting.timezone.now", return_value=at("2026-01-11T00:00:00")):
        next_day = delivery_cohort(filters)
    assert next_day["open_window_units"] == 0
    assert next_day["preliminary"] is False
