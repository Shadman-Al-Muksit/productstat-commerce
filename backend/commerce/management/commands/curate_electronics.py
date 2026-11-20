"""Replace the visible demo catalogue without deleting business evidence."""

import uuid

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from commerce.electronics_catalogue import COLORS, FAMILIES, image_url, variant_attributes
from commerce.models import AuditEvent, Product, SKU, StockMovement, User
from commerce.services import advisory_lock


NAMESPACE = uuid.UUID("cf405282-de0a-48a5-a851-79bdc8bc78db")


def catalogue_id(value):
    return uuid.uuid5(NAMESPACE, value)


class Command(BaseCommand):
    help = "Preview an electronics-only synthetic catalogue; --apply archives the previous visible catalogue and adds missing electronics. Never deletes orders, products or stock."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Apply the preview atomically. Without this flag no records change.")
        parser.add_argument("--actor", help="Optional administrator username recorded on the audit and opening-stock events.")

    @transaction.atomic
    def handle(self, *args, **options):
        advisory_lock("catalogue:curate-electronics:v1")
        actor = None
        if options["actor"]:
            actor = User.objects.filter(username=options["actor"], role="administrator", is_active=True).first()
            if actor is None:
                raise CommandError("--actor must name an active administrator.")
        ids = [catalogue_id(f"product:{family.key}") for family in FAMILIES]
        previous = list(Product.objects.select_for_update().filter(is_active=True).exclude(id__in=ids).values_list("id", flat=True))
        missing = sum(not Product.objects.filter(id=product_id).exists() for product_id in ids)
        self.stdout.write(f"Electronics preview: archive {len(previous)} currently published products; add {missing} products; target {len(FAMILIES)} products / {len(FAMILIES) * len(COLORS)} colour SKUs.")
        self.stdout.write("Prior products, SKU stock/reservations, order snapshots and financial history are retained. New opening stock is synthetic.")
        if not options["apply"]:
            self.stdout.write("Preview only. Re-run with --apply to change the visible catalogue.")
            return

        Product.objects.filter(id__in=previous).update(is_active=False)
        created_products, created_skus, republished = [], [], []
        for family_index, family in enumerate(FAMILIES):
            product_id = catalogue_id(f"product:{family.key}")
            product, created = Product.objects.get_or_create(
                id=product_id,
                defaults={"name": family.name, "slug": f"electronics-{family.key}", "category": family.category,
                          "description": family.description, "image_url": image_url(family.key, "black")},
            )
            if created:
                created_products.append(str(product.id))
            elif not product.is_active:
                product.is_active = True
                product.save(update_fields=["is_active"])
                republished.append(str(product.id))
            for color_index, color in enumerate(COLORS):
                stock = 24 + family_index * 2 + color_index * 3
                sku, created = SKU.objects.get_or_create(
                    id=catalogue_id(f"sku:{family.key}:{color[0]}"),
                    defaults={"product": product, "code": f"ELX-{family_index + 1:03d}-{color[0].upper()}",
                              "label": color[1], "attributes": variant_attributes(family, color), "price": family.price,
                              "on_hand": stock},
                )
                if created:
                    created_skus.append(str(sku.id))
                    StockMovement.objects.create(sku=sku, on_hand_delta=stock, kind="demo_opening",
                                                 reference=f"electronics-opening:{sku.id}", actor=actor)
        changed = bool(previous or created_products or created_skus or republished)
        if changed:
            AuditEvent.objects.create(actor=actor, event="catalogue_curated", entity="catalogue", reference="electronics-v1",
                                      details={"synthetic": True, "archived_product_ids": [str(value) for value in previous],
                                               "created_product_ids": created_products, "created_sku_ids": created_skus,
                                               "republished_product_ids": republished, "existing_stock_preserved": True})
        self.stdout.write(self.style.SUCCESS("Electronics catalogue applied." if changed else "Electronics catalogue already current; no records changed."))
