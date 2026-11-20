"""Curation replaces publication, never past sales or reserved inventory."""

import io

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from commerce.electronics_catalogue import COLORS, FAMILIES
from commerce.models import AuditEvent, CompanySettings, DeliveryZone, Order, OrderLine, Payment, Product, SKU, StockMovement


pytestmark = pytest.mark.django_db


@pytest.fixture
def prior_catalogue():
    product = Product.objects.create(name="Original tote", slug="original-tote", category="Bags")
    sku = SKU.objects.create(product=product, code="ORIGINAL-TOTE", price="1000.00", on_hand=12, reserved=2)
    order = Order.objects.create(number="PRIOR-ORDER", customer_name="Synthetic Customer", phone="",
                                 subtotal="2000.00", grand_total="2000.00")
    line = OrderLine.objects.create(order=order, sku=sku, sku_code=sku.code, product_name=product.name,
                                   variant_name="Original", quantity=2, unit_price=sku.price)
    payment = Payment.objects.create(order=order, method="cod", amount=order.grand_total)
    return product, sku, order, line, payment


def curate(**kwargs):
    output = io.StringIO()
    call_command("curate_electronics", stdout=output, **kwargs)
    return output.getvalue()


def test_preview_is_read_only(prior_catalogue):
    text = curate()
    assert "Preview only" in text and "archive 1" in text
    assert Product.objects.count() == 1 and SKU.objects.count() == 1
    assert Product.objects.get().is_active
    assert StockMovement.objects.count() == 0 and AuditEvent.objects.count() == 0


def test_curation_archives_publication_preserving_order_and_stock(prior_catalogue):
    product, sku, order, line, payment = prior_catalogue
    line.refresh_from_db()
    order.refresh_from_db()
    payment.refresh_from_db()
    snapshots = (line.product_name, line.variant_name, line.unit_price, line.quantity, order.grand_total, payment.amount)
    curate(apply=True)
    product.refresh_from_db()
    sku.refresh_from_db()
    order.refresh_from_db()
    line.refresh_from_db()
    payment.refresh_from_db()
    assert not product.is_active and sku.is_active
    assert (sku.on_hand, sku.reserved) == (12, 2)
    assert (line.product_name, line.variant_name, line.unit_price, line.quantity, order.grand_total, payment.amount) == snapshots
    assert Order.objects.count() == OrderLine.objects.count() == Payment.objects.count() == 1
    assert Product.objects.filter(is_active=True).count() == len(FAMILIES)
    assert SKU.objects.exclude(pk=sku.pk).count() == len(FAMILIES) * len(COLORS)
    assert StockMovement.objects.count() == len(FAMILIES) * len(COLORS)
    event = AuditEvent.objects.get(event="catalogue_curated")
    assert event.details["archived_product_ids"] == [str(product.id)]
    assert event.details["existing_stock_preserved"]


def test_repeat_curation_preserves_changed_electronics_stock_and_price(prior_catalogue):
    curate(apply=True)
    sku = SKU.objects.get(code="ELX-001-BLACK")
    sku.on_hand = 9
    sku.reserved = 3
    sku.price = "70000.00"
    sku.save(update_fields=["on_hand", "reserved", "price"])
    before = (Product.objects.count(), SKU.objects.count(), StockMovement.objects.count(), AuditEvent.objects.count())
    text = curate(apply=True)
    sku.refresh_from_db()
    assert "no records changed" in text
    assert (sku.on_hand, sku.reserved, str(sku.price)) == (9, 3, "70000.00")
    assert before == (Product.objects.count(), SKU.objects.count(), StockMovement.objects.count(), AuditEvent.objects.count())


def test_public_catalogue_excludes_archives_and_exposes_colour_images(prior_catalogue):
    curate(apply=True)
    client = APIClient()
    response = client.get("/api/v1/catalog/products/")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == len(FAMILIES)
    assert set(data["categories"]) == {family.category for family in FAMILIES}
    assert client.get("/api/v1/catalog/products/original-tote/").status_code == 404
    for product in data["results"]:
        assert len(product["skus"]) == len(COLORS)
        assert len({sku["attributes"]["image_url"] for sku in product["skus"]}) == len(COLORS)
        for sku in product["skus"]:
            assert sku["attributes"]["image_url"].startswith("/products/electronics/")
            assert sku["attributes"]["color_hex"].startswith("#")
            assert sku["attributes"]["synthetic"] is True


def test_fresh_seed_uses_electronics_without_reseeding_history(settings):
    settings.DEBUG = True
    call_command("seed_demo", orders=3, skus=42, stdout=io.StringIO())
    assert SKU.objects.count() == 42 and OrderLine.objects.count() == 9
    assert set(Product.objects.values_list("category", flat=True)) == {family.category for family in FAMILIES}
    assert all(sku.attributes["image_url"].startswith("/products/electronics/") for sku in SKU.objects.all())
    before = (Product.objects.count(), SKU.objects.count(), Order.objects.count(), OrderLine.objects.count(), StockMovement.objects.count())
    call_command("seed_demo", orders=3, skus=42, stdout=io.StringIO())
    assert before == (Product.objects.count(), SKU.objects.count(), Order.objects.count(), OrderLine.objects.count(), StockMovement.objects.count())


def test_cart_get_prunes_archived_products_and_skus_but_retains_active_lines(prior_catalogue):
    archived_product, archived_sku, *_ = prior_catalogue
    active_product = Product.objects.create(name="USB hub", slug="usb-hub", category="Accessories")
    active_sku = SKU.objects.create(product=active_product, code="ACTIVE-HUB", price="2250.00", on_hand=5)
    inactive_sku = SKU.objects.create(product=active_product, code="OLD-HUB", price="2250.00", on_hand=4, is_active=False)
    client = APIClient()
    session = client.session
    session["cart"] = {str(archived_sku.id): 2, str(inactive_sku.id): 1, str(active_sku.id): 3}
    session.save()
    archived_product.is_active = False
    archived_product.save(update_fields=["is_active"])
    response = client.get("/api/v1/cart/")
    assert response.status_code == 200
    assert [(item["sku_id"], item["quantity"]) for item in response.json()["items"]] == [(str(active_sku.id), 3)]
    assert response.json()["subtotal"] == "6750.00"
    assert client.session["cart"] == {str(active_sku.id): 3}
    archived_sku.refresh_from_db()
    assert (archived_sku.on_hand, archived_sku.reserved) == (12, 2)


@pytest.mark.parametrize("archive_product", [True, False])
def test_archived_cart_line_can_be_removed_but_not_added(prior_catalogue, archive_product):
    product, sku, *_ = prior_catalogue
    client = APIClient()
    session = client.session
    session["cart"] = {str(sku.id): 2}
    session.save()
    archived = product if archive_product else sku
    archived.is_active = False
    archived.save(update_fields=["is_active"])
    removed = client.post("/api/v1/cart/", {"sku_id": str(sku.id), "quantity": 0}, format="json")
    assert removed.status_code == 200 and removed.json()["items"] == []
    assert client.session["cart"] == {}
    rejected = client.post("/api/v1/cart/", {"sku_id": str(sku.id), "quantity": 1}, format="json")
    assert rejected.status_code == 404 and client.session["cart"] == {}
    archived.refresh_from_db()
    assert not archived.is_active


def test_checkout_after_archive_pruning_reserves_only_the_active_cart_stock(prior_catalogue):
    archived_product, archived_sku, *_ = prior_catalogue
    CompanySettings.objects.create(pk=1)
    zone = DeliveryZone.objects.create(name="Synthetic delivery zone", charge="70.00")
    product = Product.objects.create(name="Wireless mouse", slug="wireless-mouse", category="Laptops & PCs")
    sku = SKU.objects.create(product=product, code="ACTIVE-MOUSE", price="1490.00", on_hand=3)
    client = APIClient()
    session = client.session
    session["cart"] = {str(archived_sku.id): 2, str(sku.id): 2}
    session.save()
    archived_product.is_active = False
    archived_product.save(update_fields=["is_active"])
    assert client.get("/api/v1/cart/").status_code == 200
    payload = {"customer_name": "Synthetic Buyer", "email": "", "phone": "01712345678",
               "address": {"line1": "21 Test Road", "city": "Chattogram"},
               "delivery_zone_id": zone.id, "payment_method": "cod"}
    response = client.post("/api/v1/checkout/", payload, format="json", HTTP_IDEMPOTENCY_KEY="active-after-archive")
    assert response.status_code == 201
    order = Order.objects.get(id=response.json()["order"]["id"])
    assert list(order.lines.values_list("sku_id", "quantity")) == [(sku.id, 2)]
    sku.refresh_from_db()
    archived_sku.refresh_from_db()
    assert (sku.on_hand, sku.reserved, sku.available) == (3, 2, 1)
    assert (archived_sku.on_hand, archived_sku.reserved) == (12, 2)
    assert str(order.grand_total) == "3050.00"
