"""Courier settlement authorization is enforced at the financial service boundary."""

from decimal import Decimal

import pytest
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from commerce import services
from commerce.models import (AuditEvent, CompanySettings, DeliveryZone, Order, Payment,
                             PaymentSettlement, Product, SKU, StockMovement, User)


pytestmark = pytest.mark.django_db


@pytest.fixture
def collected_order():
    observed = timezone.now()
    order = Order.objects.create(
        number='QA-SETTLEMENT-PERMISSIONS', customer_name='Synthetic Customer',
        phone='', status='delivered', delivered_at=observed,
        subtotal='9980.00', shipping_total='70.00', grand_total='10050.00',
        payment_method='cod',
    )
    Payment.objects.create(order=order, method='cod', status='successful',
                           amount='10050.00', collected_at=observed)
    return order


def actor_for(kind):
    if kind == 'none':
        return None
    if kind == 'anonymous':
        return AnonymousUser()
    return User.objects.create_user(
        username='settlement-' + kind,
        role='administrator' if kind == 'inactive-administrator' else ('customer' if kind in {'superuser', 'inactive-superuser'} else kind),
        is_superuser=kind in {'superuser', 'inactive-superuser'},
        is_active=kind not in {'inactive-administrator', 'inactive-superuser'},
    )


def financial_snapshot(order):
    return {
        'order': Order.objects.filter(pk=order.pk).values().get(),
        'payment': Payment.objects.filter(order=order).values().get(),
        'settlements': list(PaymentSettlement.objects.filter(payment__order=order).order_by('pk').values()),
        'audit_count': AuditEvent.objects.count(),
        'stock_movement_count': StockMovement.objects.count(),
    }


@pytest.mark.parametrize('kind', [
    'none', 'anonymous', 'customer', 'analyst', 'operator',
    'inactive-administrator', 'inactive-superuser',
])
def test_service_rejects_unauthorized_settlement_without_side_effects(collected_order, kind):
    actor = actor_for(kind)
    before = financial_snapshot(collected_order)
    with pytest.raises(PermissionDenied, match='active administrator'):
        services.order_action(collected_order.id, 'settle_cod',
                              {'amount': '1000.00', 'reference': 'QA-BLOCKED'}, actor)
    assert financial_snapshot(collected_order) == before


@pytest.mark.parametrize('kind', [
    'none', 'customer', 'analyst', 'operator',
    'inactive-administrator', 'inactive-superuser',
])
def test_api_rejects_unauthorized_settlement_without_side_effects(collected_order, kind):
    actor = actor_for(kind)
    client = APIClient()
    if actor is not None:
        client.force_authenticate(actor)
    before = financial_snapshot(collected_order)
    response = client.post(f'/api/v1/staff/orders/{collected_order.id}/action/',
                           {'action': 'settle_cod', 'amount': '1000.00', 'reference': 'QA-BLOCKED'}, format='json')
    assert response.status_code == 403
    assert financial_snapshot(collected_order) == before


@pytest.mark.parametrize('kind', ['administrator', 'superuser'])
def test_authorized_settlement_keeps_partial_and_replay_contract(collected_order, kind):
    actor = actor_for(kind)
    client = APIClient()
    client.force_authenticate(actor)
    path = f'/api/v1/staff/orders/{collected_order.id}/action/'
    first = {'action': 'settle_cod', 'amount': '1000.00', 'reference': 'QA-PARTIAL-ONE'}
    assert client.post(path, first, format='json').status_code == 200
    before_replay = financial_snapshot(collected_order)
    assert client.post(path, first, format='json').status_code == 200
    assert financial_snapshot(collected_order) == before_replay

    second = {'action': 'settle_cod', 'amount': '9050.00', 'reference': 'QA-PARTIAL-TWO'}
    assert client.post(path, second, format='json').status_code == 200
    payment = collected_order.payments.get()
    assert payment.settled_amount == Decimal('10050.00')
    assert payment.settled_at is not None
    settlements = PaymentSettlement.objects.filter(payment=payment)
    assert settlements.count() == 2
    assert set(settlements.values_list('actor_id', flat=True)) == {actor.pk}
    assert AuditEvent.objects.filter(event='settle_cod', actor=actor).count() == 2

    completed = financial_snapshot(collected_order)
    conflict = client.post(path, {**first, 'amount': '2000.00'}, format='json')
    assert conflict.status_code == 400
    assert financial_snapshot(collected_order) == completed


def test_operator_cannot_replay_an_existing_administrator_settlement(collected_order):
    administrator = actor_for('administrator')
    data = {'amount': '1000.00', 'reference': 'QA-ADMINISTRATOR-ONLY'}
    services.order_action(collected_order.id, 'settle_cod', data, administrator)
    before = financial_snapshot(collected_order)
    with pytest.raises(PermissionDenied):
        services.order_action(collected_order.id, 'settle_cod', data, actor_for('operator'))
    assert financial_snapshot(collected_order) == before


def test_operator_retains_nonfinancial_fulfilment_and_collection(settings):
    settings.PRODUCTSTAT_DEMO = True
    operator = actor_for('operator')
    CompanySettings.objects.create(pk=1)
    zone = DeliveryZone.objects.create(name='Synthetic Zone', charge='0.00')
    product = Product.objects.create(name='Synthetic Headphones', slug='qa-operator-headphones', category='Audio')
    sku = SKU.objects.create(product=product, code='QA-OPERATOR-SKU', price='100.00', on_hand=5)
    order, _ = services.checkout(
        {str(sku.id): 1},
        {'customer_name': 'Synthetic Customer', 'phone': '01700000000', 'email': '',
         'address': {'line1': 'Synthetic House', 'city': 'Chattogram'},
         'delivery_zone_id': zone.pk, 'payment_method': 'cod'},
        'qa-operator-checkout', 'qa-operator-session',
    )
    client = APIClient()
    client.force_authenticate(operator)
    path = f'/api/v1/staff/orders/{order.id}/action/'
    for action, extra in [
        ('prepare', {}),
        ('dispatch', {'carrier': 'Synthetic Courier', 'tracking_number': 'QA-TRACKING'}),
        ('deliver', {}),
        ('collect_cod', {'amount': '100.00', 'reference': 'QA-COLLECTION'}),
    ]:
        response = client.post(path, {'action': action, **extra}, format='json')
        assert response.status_code == 200, response.json()
    order.refresh_from_db()
    assert order.status == 'delivered'
    payment = order.payments.get()
    assert payment.status == 'successful' and payment.amount == Decimal('100.00')
    assert payment.settled_amount == Decimal('0.00')
    assert not PaymentSettlement.objects.filter(payment=payment).exists()
    sku.refresh_from_db()
    assert sku.on_hand == 4 and sku.reserved == 0
