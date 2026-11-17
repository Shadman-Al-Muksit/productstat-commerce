"""Deterministic, synthetic database fixture; never resets existing business data."""
import os
import random
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from commerce.models import (AuditEvent, CompanySettings, DeliveryZone, Order, OrderLine, Payment, PaymentSettlement, Product, Refund, RefundLine,
                             ReturnLine, ReturnRequest, Shipment, ShipmentLine, SKU, StockMovement)

NAMESPACE = uuid.UUID("32bc1aa3-83bb-4ad5-b85b-b05737dbdfbb")
TZ = ZoneInfo("Asia/Dhaka")


def uid(value):
    return uuid.uuid5(NAMESPACE, value)


class Command(BaseCommand):
    help = "Create 2,000 SKUs, 25,000 synthetic historical orders and 75,000 lines without live inventory side effects."

    def add_arguments(self, parser):
        parser.add_argument("--small", action="store_true", help="Use 80 SKUs and 300 orders for quick development.")
        parser.add_argument("--orders", type=int)
        parser.add_argument("--skus", type=int)
        parser.add_argument("--as-of", help="ISO date anchoring the synthetic 12-month history; defaults to today.")

    @transaction.atomic
    def handle(self, *args, **options):
        order_count = options["orders"] or (300 if options["small"] else 25000)
        sku_count = options["skus"] or (80 if options["small"] else 2000)
        if not 1 <= order_count <= 250000 or not 5 <= sku_count <= 10000:
            raise CommandError("Choose 1–250,000 orders and 5–10,000 SKUs.")
        password = os.environ.get("DEMO_PASSWORD", "")
        viewer_password = os.environ.get("DEMO_VIEWER_PASSWORD", "")
        if not settings.DEBUG:
            if len(password) < 16 or len(viewer_password) < 16 or password == viewer_password or password == "ProductStatDemo!2026":
                raise CommandError("Non-debug seeding requires separate DEMO_PASSWORD and DEMO_VIEWER_PASSWORD of at least 16 characters; development defaults are forbidden.")
        password = password or "ProductStatDemo!2026"
        viewer_password = viewer_password or password
        User = get_user_model()
        for role in ("administrator", "operator", "analyst", "customer"):
            user, created = User.objects.get_or_create(username=role, defaults={"email": f"{role}@example.invalid", "role": role,
                                                                               "is_staff": role != "customer", "is_superuser": role == "administrator"})
            if created:
                user.set_password(viewer_password if role == "analyst" else password)
                user.save(update_fields=["password"])
        CompanySettings.objects.get_or_create(pk=1, defaults={"name": "Forma Commerce", "support_email": "support@example.invalid"})
        DeliveryZone.objects.get_or_create(name="Chattogram city", defaults={"charge": Decimal("70.00")})
        DeliveryZone.objects.get_or_create(name="Other Bangladesh districts", defaults={"charge": Decimal("120.00")})
        existing = Order.objects.filter(source="demo").count()
        if existing:
            self.stdout.write(self.style.WARNING(f"Demo history already exists ({existing:,} orders); nothing changed. Fresh database required to change its scale."))
            return
        if Product.objects.filter(id=uid("product:0")).exists():
            raise CommandError("Partial demo catalogue exists. Refusing to reset or overwrite its stock; use a fresh isolated demo database.")

        today = timezone.localdate()
        try:
            anchor = date.fromisoformat(options["as_of"]) if options["as_of"] else today
        except ValueError as exc:
            raise CommandError("--as-of must be YYYY-MM-DD.") from exc
        if anchor > today:
            raise CommandError("--as-of cannot be a future date.")
        end = min(datetime.combine(anchor, time(23, 59), TZ), timezone.now())
        beginning = end - timedelta(days=365)
        rng = random.Random(20261116)
        families = [
            ("Everyday Tote", "Bags", "tote.svg", 890, "A durable everyday carry with considered details and room for the essentials."),
            ("Studio Headphones", "Electronics", "headphones.svg", 2490, "Comfortable listening for focused work, long commutes and everyday playlists."),
            ("Arc Table Lamp", "Home", "lamp.svg", 1690, "Warm, focused light and a clean silhouette for your desk or bedside table."),
            ("Daily Water Bottle", "Lifestyle", "bottle.svg", 790, "A reusable bottle made for daily routines, errands and days outdoors."),
            ("Essential Watch", "Accessories", "watch.svg", 3490, "A simple dial and versatile finish for a reliable everyday accessory."),
            ("Studio Chair", "Furniture", "chair.svg", 5990, "An understated chair with a supportive shape for a thoughtfully arranged space."),
        ]
        products = []
        skus = []
        movements = []
        product_count = (sku_count + 4) // 5
        colors = ("Sand", "Charcoal", "Forest", "Terracotta", "Cloud")
        for index in range(product_count):
            name, category, image, price, description = families[index % len(families)]
            suffix = "" if index < 6 else f" {index // 6 + 1:02d}"
            product = Product(id=uid(f"product:{index}"), name=name + suffix, slug=f"{name.lower().replace(' ', '-')}-{index+1}",
                              category=category, description=description, image_url=f"/products/{image}")
            products.append(product)
            for variant in range(5):
                ordinal = index * 5 + variant
                if ordinal >= sku_count:
                    break
                sku = SKU(id=uid(f"sku:{ordinal}"), product=product, code=f"FRM-{ordinal+1:05d}", label=colors[variant],
                          attributes={"color": colors[variant]}, price=Decimal(price + 50 * (index // 6)),
                          cost=Decimal(price) * Decimal("0.55"), on_hand=0 if ordinal % 67 == 0 else rng.randint(20, 120))
                skus.append(sku)
                movements.append(StockMovement(sku=sku, on_hand_delta=sku.on_hand, kind="demo_opening", reference=f"demo-opening:{ordinal}"))
        Product.objects.bulk_create(products, batch_size=1000)
        SKU.objects.bulk_create(skus, batch_size=1000)
        StockMovement.objects.bulk_create(movements, batch_size=1000)

        orders, lines, shipments, shipment_lines, payments, returns, return_lines, refunds, refund_lines, settlements = ([] for _ in range(10))
        for index in range(order_count):
            ordered_at = beginning + timedelta(seconds=int(365 * 86400 * index / order_count))
            age = (end - ordered_at).days
            draw = rng.random()
            state = "cancelled" if draw < .05 else "failed" if draw < .10 else "returned_to_origin" if draw < .14 else "delivered"
            if age < 3 and state == "delivered":
                state = "confirmed" if age < 1 else "dispatched"
            shipped = state in {"dispatched", "delivered", "failed", "returned_to_origin"}
            delivered_at = ordered_at + timedelta(days=2) if state == "delivered" else None
            completed_at = ordered_at + timedelta(days=2) if state in {"delivered", "failed", "returned_to_origin"} else None
            if completed_at and completed_at > end:
                state, delivered_at, completed_at = "dispatched", None, None
            shipping = Decimal("70.00") if index % 3 else Decimal("120.00")
            order = Order(id=uid(f"order:{index}"), number=f"DEMO-{index+1:07d}", source="demo", external_id=str(index+1), is_historical=True,
                          customer_name=f"Demo Customer {index+1}", email=f"buyer{index+1}@example.invalid", phone="", address={"district": "Chattogram", "synthetic": True},
                          created_at=ordered_at, confirmed_at=ordered_at, dispatched_at=ordered_at + timedelta(hours=12) if shipped else None,
                          delivered_at=delivered_at, cancelled_at=ordered_at + timedelta(hours=2) if state == "cancelled" else None,
                          status=state, payment_method="cod" if index % 5 else "sslcommerz", shipping_total=shipping)
            order_lines = []
            shipment = Shipment(id=uid(f"shipment:{index}"), order=order, state=state, carrier="Demo Courier", tracking_number=f"DEMO-TRK-{index+1}",
                                dispatched_at=ordered_at + timedelta(hours=12), delivered_at=delivered_at, completed_at=completed_at) if shipped else None
            if shipment:
                shipments.append(shipment)
            for position in range(3):
                sku = skus[rng.randrange(len(skus))]
                quantity = rng.randint(1, 3)
                returned_quantity = 1 if delivered_at and age >= 8 and rng.random() < .065 else 0
                returned_at = delivered_at + timedelta(days=rng.randint(2, 5)) if returned_quantity else None
                line = OrderLine(id=uid(f"line:{index}:{position}"), order=order, sku=sku, sku_code=sku.code, product_name=sku.product.name, variant_name=sku.label,
                                 source_line_id=str(position+1), quantity=quantity, cancelled_quantity=quantity if state == "cancelled" else 0,
                                 shipped_quantity=quantity if shipped else 0, delivered_quantity=quantity if state == "delivered" else 0,
                                 returned_quantity=returned_quantity, unit_price=sku.price, delivered_at=delivered_at, returned_at=returned_at)
                order_lines.append(line)
                lines.append(line)
                if shipment:
                    shipment_lines.append(ShipmentLine(shipment=shipment, order_line=line, quantity=quantity))
                if returned_quantity:
                    returned = ReturnRequest(id=uid(f"return:{index}:{position}"), order=order, status="inspected", reason="Synthetic: size or preference",
                                             received_at=returned_at - timedelta(hours=2), inspected_at=returned_at)
                    returns.append(returned)
                    return_lines.append(ReturnLine(order_line=line, return_request=returned, quantity=returned_quantity,
                                                   accepted_quantity=returned_quantity, restock_quantity=0, disposition="quarantine"))
                    refund = Refund(id=uid(f"refund:{index}:{position}"), order=order, return_request=returned,
                                    amount=sku.price, status="confirmed", reason="Synthetic accepted return", reference=f"DEMO-REF-{index}-{position}", confirmed_at=returned_at + timedelta(hours=1))
                    refunds.append(refund)
                    refund_lines.append(RefundLine(refund=refund, order_line=line, amount=refund.amount))
            order.subtotal = sum(line.unit_price * line.quantity for line in order_lines)
            order.grand_total = order.subtotal + shipping
            orders.append(order)
            if state == "delivered":
                settled = age > 5 and index % 9 != 0
                payment = Payment(order=order, method=order.payment_method, status="successful", amount=order.grand_total,
                                        provider_transaction_id=f"demo-payment-{index}", collected_at=delivered_at,
                                        settled_amount=order.grand_total if settled else Decimal(0), settled_at=delivered_at + timedelta(days=2) if settled else None)
                payments.append(payment)
                if settled:
                    settlements.append(PaymentSettlement(id=uid(f"settlement:{index}"), payment=payment, amount=payment.settled_amount,
                                                         settled_at=payment.settled_at, reference=f"demo-settlement-{index}", source="demo"))
        for model, objects in [(Order, orders), (OrderLine, lines), (Shipment, shipments), (ShipmentLine, shipment_lines),
                               (Payment, payments), (PaymentSettlement, settlements), (ReturnRequest, returns), (ReturnLine, return_lines), (Refund, refunds), (RefundLine, refund_lines)]:
            model.objects.bulk_create(objects, batch_size=1000)
            self.stdout.write(f"{model.__name__}: {len(objects):,}")
        AuditEvent.objects.create(event="seed_completed", entity="demo", reference="synthetic-history",
                                  details={"skus": sku_count, "orders": order_count, "lines": len(lines)})
        self.stdout.write(self.style.SUCCESS(f"Seeded {sku_count:,} SKUs, {order_count:,} orders and {len(lines):,} lines across 365 days. Synthetic history did not alter catalogue inventory."))
