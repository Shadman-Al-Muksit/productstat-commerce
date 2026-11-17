"""Real PostgreSQL contention tests: independent DB connections, not mocks."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import pytest
from django.db import connections, close_old_connections
from rest_framework.exceptions import ValidationError
from commerce.models import DeliveryZone, Order, Product, SKU, StockMovement
from commerce.services import checkout


def exercise(sku_id, zone_id, attempts, key_for, identity_for):
    barrier = Barrier(attempts)
    data = {'customer_name': 'Synthetic contention buyer', 'email': '', 'phone': '01700000000',
            'address': {'street': 'Synthetic test address', 'district': 'Dhaka'},
            'delivery_zone_id': zone_id, 'payment_method': 'cod'}

    def buy(i):
        close_old_connections()
        try:
            barrier.wait(timeout=30)
            order, created = checkout({str(sku_id): 1}, data, key_for(i), identity_for(i))
            return {'id': str(order.id), 'created': created}
        except ValidationError:
            return {'rejected': True}
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=attempts) as executor:
        return list(executor.map(buy, range(attempts)))


@pytest.mark.django_db(transaction=True)
def test_fifty_buyers_cannot_oversell_five_units():
    product = Product.objects.create(name='Contention product', slug='contention-product', category='Test')
    sku = SKU.objects.create(product=product, code='CONTENTION-5', price=Decimal('100.00'), on_hand=5)
    zone = DeliveryZone.objects.create(name='Contention zone', charge=Decimal('80.00'))
    results = exercise(sku.id, zone.id, 50, lambda i: f'contention-{i}', lambda i: f'buyer-{i}')
    sku.refresh_from_db()
    assert sum('id' in result for result in results) == 5
    assert sum('rejected' in result for result in results) == 45
    assert Order.objects.count() == 5
    assert sku.on_hand == 5 and sku.reserved == 5 and sku.available == 0
    assert StockMovement.objects.filter(kind='reserve').count() == 5


@pytest.mark.django_db(transaction=True)
def test_concurrent_checkout_retries_create_exactly_one_order():
    product = Product.objects.create(name='Retry product', slug='retry-product', category='Test')
    sku = SKU.objects.create(product=product, code='RETRY-ONE', price=Decimal('120.00'), on_hand=5)
    zone = DeliveryZone.objects.create(name='Retry zone', charge=Decimal('80.00'))
    results = exercise(sku.id, zone.id, 12, lambda _: 'shared-checkout-key', lambda _: 'same-buyer')
    sku.refresh_from_db()
    assert len({result['id'] for result in results}) == 1
    assert sum(result['created'] for result in results) == 1
    assert Order.objects.count() == 1 and sku.reserved == 1
