"""Public product/variant images retain metadata and cannot mutate stock/history."""

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from commerce.models import AuditEvent, Order, OrderLine, Product, SKU, StockMovement, User
from commerce.serializers import ProductWriteSerializer, SKUWriteSerializer


pytestmark = pytest.mark.django_db


@pytest.fixture
def image_product():
    product = Product.objects.create(name='Synthetic QA Headphones', slug='synthetic-qa-headphones',
                                     category='Audio', image_url='/products/electronics/headphones-black.svg')
    sku = SKU.objects.create(product=product, code='QA-IMAGE-BLACK', label='Black', price='4990.00',
                             on_hand=12, reserved=2, attributes={
                                 'image_url': '/products/electronics/headphones-black.svg',
                                 'color': 'Black', 'color_hex': '#252b32',
                                 'specification': 'Wireless · Over-ear', 'synthetic': True,
                                 'supplier_metadata': {'source': 'retained'},
                             })
    order = Order.objects.create(number='QA-IMAGE-ORDER', customer_name='Synthetic Customer', phone='',
                                 subtotal='9980.00', grand_total='9980.00')
    line = OrderLine.objects.create(order=order, sku=sku, sku_code=sku.code, product_name=product.name,
                                   variant_name=sku.label, quantity=2, unit_price='4990.00')
    return product, sku, order, line


def authenticated_client(role):
    user = User.objects.create_user(username=f'image-{role}', role=role)
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.mark.parametrize('image_url', [
    '', '/products/tote.svg', '/products/electronics/headphones-blue.svg',
    '/products/electronics/headphones-blue.svg?v=2',
    'https://images.example.com/headphones-blue.jpg',
    'https://images.example.com:8443/catalog/blue%20headphones.jpg?version=2',
])
def test_product_and_variant_accept_public_image_references(image_product, image_url):
    product, sku, _, _ = image_product
    product_input = ProductWriteSerializer(product, data={'image_url': image_url}, partial=True)
    assert product_input.is_valid(), product_input.errors
    assert product_input.validated_data['image_url'] == image_url
    variant_input = SKUWriteSerializer(data={'id': str(sku.id), 'attributes': {'image_url': image_url}})
    assert variant_input.is_valid(), variant_input.errors
    assert variant_input.validated_data['attributes']['image_url'] == image_url


@pytest.mark.parametrize('image_url', [
    'javascript:alert(1)', 'data:image/svg+xml;base64,PHN2Zz4=',
    'http://images.example.com/unsafe.jpg', '//images.example.com/image.jpg',
    'https:/missing-host/image.jpg', 'https://',
    'https://user:password@images.example.com/image.jpg',
    'https://images.example.com:99999/image.jpg',
    '/private_media/customer-file.png', '/products/', '/products//camera.svg',
    '/products/../private_media/image.jpg', '/products/%2e%2e/private_media/image.jpg',
    '/products/%252e%252e/private_media/image.jpg',
    '/products/electronics/%2f..%2f..%2fprivate_media/image.jpg',
    '/products/electronics/%3F/../../private_media/image.jpg',
    '/products/electronics/..\\private_media/image.jpg',
    '/products/electronics/%255cprivate_media/image.jpg',
    '/products/electronics/image%0a.jpg', '/products/electronics/image\x7f.jpg',
    '/products/image%ZZ.jpg', 'https://images.example.com/' + 'x' * 1000,
])
def test_product_and_variant_reject_unsafe_image_references(image_product, image_url):
    product, sku, _, _ = image_product
    product_input = ProductWriteSerializer(product, data={'image_url': image_url}, partial=True)
    assert not product_input.is_valid()
    assert 'image_url' in product_input.errors
    variant_input = SKUWriteSerializer(data={'id': str(sku.id), 'attributes': {'image_url': image_url}})
    assert not variant_input.is_valid()
    assert 'attributes' in variant_input.errors


@pytest.mark.parametrize('attributes', [
    {'image_url': None}, {'image_url': 123}, {'image_url': []},
    {'color': 123}, {'color': 'Blue\nInjected'}, {'color': 'x' * 121},
    {'color_hex': 'blue'}, {'color_hex': '#12345'}, {'color_hex': None},
    [], 'image_url',
])
def test_variant_attributes_reject_invalid_types_and_colours(image_product, attributes):
    _, sku, _, _ = image_product
    serializer = SKUWriteSerializer(data={'id': str(sku.id), 'attributes': attributes})
    assert not serializer.is_valid()
    assert 'attributes' in serializer.errors


@pytest.mark.parametrize('color_hex', ['', '#abc', '#A1B2C3'])
def test_variant_accepts_blank_or_hex_colours_and_preserves_other_metadata(image_product, color_hex):
    _, sku, _, _ = image_product
    attributes = {**sku.attributes, 'image_url': '', 'color': '', 'color_hex': color_hex}
    serializer = SKUWriteSerializer(data={'id': str(sku.id), 'attributes': attributes})
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data['attributes'] == attributes


def preserved_state(product, sku, order, line):
    for record in (product, sku, order, line):
        record.refresh_from_db()
    return {
        'product': (product.name, product.image_url),
        'sku': (sku.attributes, sku.on_hand, sku.reserved, sku.price),
        'order': (order.number, order.subtotal, order.grand_total),
        'line': (line.product_name, line.variant_name, line.unit_price, line.quantity),
        'movements': StockMovement.objects.count(),
        'audits': AuditEvent.objects.count(),
    }


@pytest.mark.parametrize('role', ['administrator', 'operator'])
def test_authorized_image_edit_preserves_metadata_stock_and_order_snapshots(image_product, role):
    product, sku, order, line = image_product
    before = preserved_state(product, sku, order, line)
    attributes = {**sku.attributes, 'color': 'Blue', 'color_hex': '#416d94',
                  'image_url': '/products/electronics/headphones-blue.svg'}
    client = authenticated_client(role)
    response = client.patch(f'/api/v1/staff/products/{product.id}/', {
        'image_url': 'https://images.example.com/catalog/headphones.jpg',
        'skus': [{'id': str(sku.id), 'attributes': attributes, 'on_hand': 999, 'reserved': 0}],
    }, format='json')
    assert response.status_code == 200, response.json()
    after = preserved_state(product, sku, order, line)
    assert after['sku'] == (attributes, 12, 2, Decimal('4990.00'))
    assert after['order'] == before['order'] and after['line'] == before['line']
    assert after['movements'] == before['movements']
    assert after['audits'] == before['audits'] + 1
    assert product.image_url == 'https://images.example.com/catalog/headphones.jpg'
    public = client.get(f'/api/v1/catalog/products/{product.slug}/').json()
    assert public['image_url'] == product.image_url
    assert public['skus'][0]['attributes'] == attributes


def test_omitted_variant_attributes_do_not_erase_existing_image_metadata(image_product):
    product, sku, order, line = image_product
    before = preserved_state(product, sku, order, line)
    response = authenticated_client('operator').patch(f'/api/v1/staff/products/{product.id}/', {
        'description': 'Updated synthetic description', 'skus': [{'id': str(sku.id), 'label': 'Black finish'}],
    }, format='json')
    assert response.status_code == 200, response.json()
    after = preserved_state(product, sku, order, line)
    assert after['sku'] == before['sku']
    assert after['order'] == before['order'] and after['line'] == before['line']


@pytest.mark.parametrize('bad_patch', [
    {'image_url': 'javascript:alert(1)'},
    {'skus': [{'attributes': {'image_url': 'data:image/svg+xml,unsafe'}}]},
    {'skus': [{'attributes': {'color_hex': '#12'}}]},
])
def test_invalid_image_patch_is_atomic(image_product, bad_patch):
    product, sku, order, line = image_product
    if 'skus' in bad_patch:
        bad_patch = {'skus': [{**bad_patch['skus'][0], 'id': str(sku.id)}]}
    before = preserved_state(product, sku, order, line)
    response = authenticated_client('administrator').patch(
        f'/api/v1/staff/products/{product.id}/', {'name': 'Must not save', **bad_patch}, format='json')
    assert response.status_code == 400
    assert preserved_state(product, sku, order, line) == before


@pytest.mark.parametrize('role', ['analyst', 'customer'])
def test_read_only_roles_cannot_change_product_or_variant_images(image_product, role):
    product, sku, order, line = image_product
    before = preserved_state(product, sku, order, line)
    response = authenticated_client(role).patch(f'/api/v1/staff/products/{product.id}/', {
        'image_url': '/products/electronics/headphones-blue.svg',
        'skus': [{'id': str(sku.id), 'attributes': {'image_url': '/products/electronics/headphones-blue.svg'}}],
    }, format='json')
    assert response.status_code == 403
    assert preserved_state(product, sku, order, line) == before


def test_blank_variant_image_enables_product_image_fallback(image_product):
    product, sku, _, _ = image_product
    attributes = {**sku.attributes, 'image_url': '', 'color_hex': ''}
    response = authenticated_client('operator').patch(f'/api/v1/staff/products/{product.id}/', {
        'skus': [{'id': str(sku.id), 'attributes': attributes}],
    }, format='json')
    assert response.status_code == 200, response.json()
    sku.refresh_from_db()
    assert sku.attributes['image_url'] == '' and sku.attributes['color_hex'] == ''
    assert sku.attributes['specification'] == attributes['specification']
    product.refresh_from_db()
    assert product.image_url == '/products/electronics/headphones-black.svg'
