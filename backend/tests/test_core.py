from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock,patch
from threading import Barrier
import pytest
from django.conf import settings
from django.db import connection
from django.db import IntegrityError,transaction
from django.db import close_old_connections,connections
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient
from commerce.models import CompanySettings,DeliveryZone,Order,OrderLine,Product,SKU,User,Refund,RefundLine,StockMovement,Payment,PaymentSettlement,ReturnRequest,OutboxEvent,AuditEvent
from commerce import services,payments

pytestmark=pytest.mark.django_db

@pytest.fixture(autouse=True)
def demo_test_settings(settings):
    settings.PRODUCTSTAT_DEMO=True

@pytest.fixture
def catalog():
    CompanySettings.objects.create(pk=1)
    zone=DeliveryZone.objects.create(name='Chattogram',charge='90.00')
    product=Product.objects.create(name='Travel Bag',slug='travel-bag',category='Bags',image_url='/products/bag.svg')
    sku=SKU.objects.create(product=product,code='BAG-01',label='Black',price='1000.00',on_hand=10)
    return zone,product,sku

@pytest.fixture
def payload(catalog):
    return {'customer_name':'Test Customer','email':'','phone':'01712345678','address':{'line1':'21 Test Road','city':'Chattogram'},'delivery_zone_id':catalog[0].id,'payment_method':'cod'}

@pytest.fixture
def admin(): return User.objects.create_user(username='administrator',password='A-safe-password-729!',role='administrator')

def place(catalog,payload,quantity=3,key='key-1'):
    return services.checkout({str(catalog[2].id):quantity},payload,key,'session-A')[0]

def deliver(order,admin):
    services.order_action(order.id,'dispatch',{'carrier':'Test courier','tracking_number':'TRACK-1'},admin)
    services.order_action(order.id,'deliver',{},admin)

def test_reservation_cancellation_and_idempotency(catalog,payload):
    order=place(catalog,payload)
    sku=catalog[2];sku.refresh_from_db()
    assert sku.available==7 and sku.reserved==3
    repeated,created=services.checkout({},payload,'key-1','session-A')
    assert repeated.id==order.id and not created
    with pytest.raises(ValidationError): services.checkout({},payload,'key-1','session-B')
    services.cancel_order(order.id)
    sku.refresh_from_db();order.refresh_from_db()
    assert sku.available==10 and sku.reserved==0 and order.status=='cancelled'
    assert StockMovement.objects.filter(reference=str(order.id)).count()==2

def test_oversell_rolls_back_complete_checkout(catalog,payload):
    with pytest.raises(ValidationError): place(catalog,payload,quantity=11)
    assert not Order.objects.exists()
    sku=catalog[2];sku.refresh_from_db();assert sku.reserved==0

def test_partial_cancellation_cod_collection_and_settlement(catalog,payload,admin):
    order=place(catalog,payload)
    line=order.lines.get()
    services.cancel_order(order.id,admin,[{'order_line_id':str(line.id),'quantity':1}])
    deliver(order,admin)
    services.order_action(order.id,'collect_cod',{'amount':'2090.00','reference':'courier-1'},admin)
    services.order_action(order.id,'settle_cod',{'amount':'2000.00','reference':'bank-1'},admin)
    payment=order.payments.get();assert payment.amount==Decimal('2090') and payment.settled_amount==Decimal('2000')
    with pytest.raises(ValidationError): services.order_action(order.id,'settle_cod',{'amount':'100.00','reference':'bank-2'},admin)
    sku=catalog[2];sku.refresh_from_db();assert sku.on_hand==8 and sku.reserved==0

def test_partial_settlements_keep_original_dates_and_references(catalog,payload,admin):
    from commerce.reporting import cash_activity
    from django.utils import timezone as clock
    order=place(catalog,payload);deliver(order,admin)
    services.order_action(order.id,'collect_cod',{'amount':'3090','reference':'collected'},admin)
    day_one=clock.now()-timedelta(days=2);day_two=day_one+timedelta(days=1)
    with patch('commerce.services.timezone.now',return_value=day_one):
        services.order_action(order.id,'settle_cod',{'amount':'1000','reference':'bank-day-1'},admin)
    with patch('commerce.services.timezone.now',return_value=day_two):
        services.order_action(order.id,'settle_cod',{'amount':'2090','reference':'bank-day-2'},admin)
        services.order_action(order.id,'settle_cod',{'amount':'2090','reference':'bank-day-2'},admin)
    payment=order.payments.get();assert payment.settled_amount==Decimal('3090') and payment.settled_at==day_two
    assert payment.settlements.count()==2
    assert payment.settlements.get(reference='bank-day-1').settled_at==day_one
    for date,amount in [(clock.localdate(day_one),Decimal('1000')),(clock.localdate(day_two),Decimal('2090'))]:
        cash=cash_activity({'start':date,'end':date,'product_ids':[]})
        assert Decimal(cash['settled_amount'])==amount
    with pytest.raises(ValidationError):
        services.order_action(order.id,'settle_cod',{'amount':'100','reference':'bank-day-2'},admin)
    assert payment.settlements.count()==2
    assert AuditEvent.objects.filter(event='settle_cod',reference=str(order.id)).count()==2

def test_settlement_events_are_immutable_and_positive(catalog,payload,admin):
    from django.core.exceptions import ValidationError as ModelValidationError
    order=place(catalog,payload);deliver(order,admin)
    services.order_action(order.id,'collect_cod',{'amount':'3090','reference':'collection'},admin)
    services.order_action(order.id,'settle_cod',{'amount':'1000','reference':'bank-1'},admin)
    event=order.payments.get().settlements.get()
    event.amount=Decimal('1')
    with pytest.raises(ModelValidationError): event.save()
    with pytest.raises(ModelValidationError): PaymentSettlement.objects.filter(pk=event.pk).update(amount=Decimal('1'))
    with pytest.raises(ModelValidationError): event.delete()
    with pytest.raises(IntegrityError),transaction.atomic():
        PaymentSettlement.objects.create(payment=event.payment,amount=0,settled_at=timezone.now(),reference='invalid-zero')

def test_settlement_backfill_recovers_reconciled_audits_and_labels_legacy(catalog,payload,admin):
    import importlib
    from django.apps import apps
    from types import SimpleNamespace
    observed=timezone.now()-timedelta(days=1)
    recovered=place(catalog,payload,key='recover-audits');payment=recovered.payments.get()
    payment.status='successful';payment.collected_at=observed-timedelta(days=2);payment.settled_amount=Decimal('300');payment.settled_at=observed;payment.save()
    first=AuditEvent.objects.create(event='settle_cod',entity='order',reference=str(recovered.id),actor=admin,details={'amount':'100.00','reference':'first-reference'})
    second=AuditEvent.objects.create(event='settle_cod',entity='order',reference=str(recovered.id),actor=admin,details={'amount':'200.00','reference':'second-reference'})
    legacy=place(catalog,payload,quantity=1,key='legacy-snapshot');legacy.is_historical=True;legacy.save()
    historical=legacy.payments.get();historical.settled_amount=Decimal('50');historical.settled_at=observed;historical.save()
    incomplete=place(catalog,payload,quantity=1,key='incomplete-audit');partial=incomplete.payments.get();partial.settled_amount=Decimal('90');partial.settled_at=None;partial.save()
    AuditEvent.objects.create(event='settle_cod',entity='order',reference=str(incomplete.id),details={'amount':'10','reference':'incomplete'})
    migration=importlib.import_module('commerce.migrations.0004_backfill_payment_settlements')
    migration.backfill_settlements(apps,SimpleNamespace(connection=connection))
    events=list(payment.settlements.order_by('settled_at'))
    assert [(event.amount,event.reference,event.source) for event in events]==[(Decimal('100'),'first-reference','audit_backfill'),(Decimal('200'),'second-reference','audit_backfill')]
    assert events[0].settled_at==first.created_at and events[1].settled_at==second.created_at
    fallback=historical.settlements.get();assert fallback.amount==Decimal('50') and fallback.settled_at==observed and fallback.source=='legacy_aggregate'
    unknown=partial.settlements.get();assert unknown.amount==Decimal('90') and unknown.settled_at is None and unknown.source=='legacy_aggregate'
    migration.backfill_settlements(apps,SimpleNamespace(connection=connection))
    assert PaymentSettlement.objects.count()==4

def test_partial_return_restock_refund_and_replay(catalog,payload,admin):
    order=place(catalog,payload);deliver(order,admin)
    services.order_action(order.id,'collect_cod',{'amount':'3090.00','reference':'courier-1'},admin)
    line=order.lines.get()
    request=services.request_return(order.id,{'reason':'Wrong size','lines':[{'order_line_id':str(line.id),'quantity':2}]})
    services.return_action(request.id,'approve',{},admin);services.return_action(request.id,'receive',{},admin)
    returned=request.lines.get()
    services.return_action(request.id,'inspect',{'lines':[{'id':str(returned.id),'accepted_quantity':2,'restock_quantity':1,'disposition':'restock'}]},admin)
    line.refresh_from_db();sku=catalog[2];sku.refresh_from_db()
    assert line.returned_quantity==2 and sku.on_hand==8
    refund=order.refunds.get();assert refund.amount==Decimal('2000')
    assert RefundLine.objects.get(refund=refund).amount==Decimal('2000')
    services.confirm_refund(refund.id,'bank-refund-1',admin)
    services.confirm_refund(refund.id,'bank-refund-1',admin)
    with pytest.raises(ValidationError): services.confirm_refund(refund.id,'another-reference',admin)
    with pytest.raises(ValidationError): services.return_action(request.id,'inspect',{},admin)
    with pytest.raises(ValidationError): services.request_return(order.id,{'reason':'Again','lines':[{'order_line_id':str(line.id),'quantity':2}]})

def test_uncollected_return_reduces_cod_due_without_fake_refund(catalog,payload,admin):
    order=place(catalog,payload);deliver(order,admin);line=order.lines.get()
    request=services.request_return(order.id,{'reason':'Wrong size','lines':[{'order_line_id':str(line.id),'quantity':1}]})
    services.return_action(request.id,'approve',{},admin);services.return_action(request.id,'receive',{},admin)
    services.return_action(request.id,'inspect',{'lines':[{'id':str(request.lines.get().id),'accepted_quantity':1,'restock_quantity':0,'disposition':'quarantine'}]},admin)
    assert not order.refunds.exists()
    services.order_action(order.id,'collect_cod',{'amount':'2090','reference':'receipt'},admin)
    assert services.collected(order)==Decimal('2090')

def test_guest_access_and_role_boundaries(catalog,payload,admin):
    order=place(catalog,payload);client=APIClient()
    assert client.get(f'/api/v1/orders/{order.id}/').status_code==403
    assert client.get(f'/api/v1/orders/{order.id}/?token={services.token_for(order)}').status_code==200
    analyst=User.objects.create_user(username='analyst',role='analyst')
    client.force_authenticate(analyst)
    assert client.get('/api/v1/staff/orders/').status_code==403
    assert client.post('/api/v1/staff/inventory/',{'sku_id':str(catalog[2].id),'delta':1,'reason':'x'},format='json').status_code==403
    client.force_authenticate(admin)
    assert client.get('/api/v1/staff/orders/').status_code==200

def test_csrf_required_for_anonymous_cart_login_and_checkout(catalog,payload):
    client=APIClient(enforce_csrf_checks=True)
    assert client.post('/api/v1/cart/',{'sku_id':str(catalog[2].id),'quantity':1},format='json').status_code==403
    assert client.post('/api/v1/auth/login/',{'username':'x','password':'x'},format='json').status_code==403
    bootstrap=client.get('/api/v1/bootstrap/')
    token=bootstrap.json()['csrfToken']
    response=client.post('/api/v1/cart/',{'sku_id':str(catalog[2].id),'quantity':1},format='json',HTTP_X_CSRFTOKEN=token)
    assert response.status_code==200
    response=client.post('/api/v1/checkout/',payload,format='json',HTTP_X_CSRFTOKEN=token,HTTP_IDEMPOTENCY_KEY='csrf-checkout')
    assert response.status_code==201

def test_live_checkout_api_retries_after_cleared_cart(catalog,payload):
    client=APIClient()
    client.post('/api/v1/cart/',{'sku_id':str(catalog[2].id),'quantity':2},format='json')
    response=client.post('/api/v1/checkout/',payload,format='json',HTTP_IDEMPOTENCY_KEY='checkout-retry')
    assert response.status_code==201
    repeated=client.post('/api/v1/checkout/',payload,format='json',HTTP_IDEMPOTENCY_KEY='checkout-retry')
    assert repeated.status_code==200
    assert repeated.json()['order']['id']==response.json()['order']['id']
    assert repeated.json()['access_token']==response.json()['access_token']

def test_reused_key_with_changed_nonempty_cart_keeps_cart_intact(catalog,payload):
    client=APIClient()
    client.post('/api/v1/cart/',{'sku_id':str(catalog[2].id),'quantity':2},format='json')
    original=client.post('/api/v1/checkout/',payload,format='json',HTTP_IDEMPOTENCY_KEY='changed-cart-key')
    assert original.status_code==201
    client.post('/api/v1/cart/',{'sku_id':str(catalog[2].id),'quantity':1},format='json')
    rejected=client.post('/api/v1/checkout/',payload,format='json',HTTP_IDEMPOTENCY_KEY='changed-cart-key')
    assert rejected.status_code==400
    assert client.get('/api/v1/cart/').json()['items'][0]['quantity']==1
    assert Order.objects.count()==1

def test_django_admin_changes_create_atomic_audit_revision(catalog,admin,monkeypatch):
    from django.contrib import admin as admin_site
    from django.test import RequestFactory
    from commerce.models import AuditEvent
    from commerce.admin import AuditedAdmin
    model_admin=AuditedAdmin(Product,admin_site.site)
    request=RequestFactory().post('/admin/commerce/product/');request.user=admin
    product=catalog[1];product.name='Audited change'
    model_admin.save_model(request,product,None,True)
    assert AuditEvent.objects.filter(event='admin_updated',reference=str(product.pk)).count()==1
    def fail_audit(*args,**kwargs): raise RuntimeError('Audit unavailable')
    monkeypatch.setattr('commerce.admin.audit',fail_audit)
    product.name='Must roll back'
    with pytest.raises(RuntimeError): model_admin.save_model(request,product,None,True)
    product.refresh_from_db();assert product.name=='Audited change'

def test_gateway_initiation_is_in_same_audited_revision(catalog,payload,settings):
    from commerce.models import AuditEvent
    settings.SSLCOMMERZ_STORE_ID='test';settings.SSLCOMMERZ_STORE_PASSWORD='test';settings.PRODUCTSTAT_DEMO=True
    order=place(catalog,{**payload,'payment_method':'sslcommerz'})
    response=Mock();response.json.return_value={'status':'SUCCESS','GatewayPageURL':'https://sandbox.sslcommerz.com/pay/example'}
    with patch('commerce.payments.requests.post',return_value=response):
        assert payments.initiate(order)=='https://sandbox.sslcommerz.com/pay/example'
    assert AuditEvent.objects.filter(event='payment_initiated',reference=str(order.id)).count()==1

def test_history_cannot_mutate_stock_or_payments(catalog,payload,admin):
    order=place(catalog,payload);order.is_historical=True;order.save()
    with pytest.raises(ValidationError): services.cancel_order(order.id,admin)
    with pytest.raises(ValidationError): services.order_action(order.id,'dispatch',{},admin)

@pytest.mark.parametrize('callback_status',['INVALID','FAILED'])
def test_payment_callback_cannot_trust_posted_success(catalog,payload,settings,callback_status):
    settings.SSLCOMMERZ_STORE_ID='test';settings.SSLCOMMERZ_STORE_PASSWORD='test'
    data={**payload,'payment_method':'sslcommerz'};order=place(catalog,data)
    payment=order.payments.get()
    response=Mock();response.json.return_value={'status':callback_status,'tran_id':payment.provider_transaction_id,'currency':'BDT','amount':'3090.00'}
    with patch('commerce.payments.requests.get',return_value=response):
        with pytest.raises(ValidationError): payments.validate_callback({'tran_id':payment.provider_transaction_id,'val_id':'bad','status':'VALID'})
    order.refresh_from_db();assert order.status=='pending_payment'

def test_valid_payment_replay_expiry_and_late_capture(catalog,payload,settings):
    settings.SSLCOMMERZ_STORE_ID='test';settings.SSLCOMMERZ_STORE_PASSWORD='test'
    order=place(catalog,{**payload,'payment_method':'sslcommerz'})
    order.reservation_expires_at=timezone.now()-timedelta(minutes=1);order.save()
    assert services.expire_reservations()==1
    payment=order.payments.get()
    response=Mock();response.json.return_value={'status':'VALID','tran_id':payment.provider_transaction_id,'currency':'BDT','amount':'3090.00'}
    with patch('commerce.payments.requests.get',return_value=response):
        payments.validate_callback({'tran_id':payment.provider_transaction_id,'val_id':'verified'})
        payments.validate_callback({'tran_id':payment.provider_transaction_id,'val_id':'verified'})
    payment.refresh_from_db();order.refresh_from_db();sku=catalog[2];sku.refresh_from_db()
    assert order.status=='cancelled' and payment.status=='exception' and sku.reserved==0
    assert order.refunds.count()==1 and order.refunds.get().amount==Decimal('3090')

def test_payment_amount_and_currency_mismatch_rejected(catalog,payload,settings):
    settings.SSLCOMMERZ_STORE_ID='test';settings.SSLCOMMERZ_STORE_PASSWORD='test'
    order=place(catalog,{**payload,'payment_method':'sslcommerz'});payment=order.payments.get()
    response=Mock();response.json.return_value={'status':'VALID','tran_id':payment.provider_transaction_id,'currency':'BDT','amount':'1.00'}
    with patch('commerce.payments.requests.get',return_value=response):
        with pytest.raises(ValidationError): payments.validate_callback({'tran_id':payment.provider_transaction_id,'val_id':'mismatch'})
    assert services.collected(order)==0

def test_unconfigured_gateway_returns_503_without_reservation(catalog,payload):
    client=APIClient();client.post('/api/v1/cart/',{'sku_id':str(catalog[2].id),'quantity':1},format='json')
    response=client.post('/api/v1/checkout/',{**payload,'payment_method':'sslcommerz'},format='json',HTTP_IDEMPOTENCY_KEY='no-credentials')
    assert response.status_code==503
    assert not Order.objects.exists()

def test_list_order_queries_are_bounded(catalog,payload,admin):
    for number in range(6): place(catalog,payload,quantity=1,key=f'order-{number}')
    client=APIClient();client.force_authenticate(admin)
    with CaptureQueriesContext(connection) as captured:
        response=client.get('/api/v1/staff/orders/?page=2&page_size=3')
    assert response.status_code==200 and response.json()['count']==6 and len(response.json()['results'])==3
    assert len(captured)<20

def test_tax_is_snapshotted_and_refunded_proportionately(catalog,payload,admin):
    company=CompanySettings.objects.get(pk=1);company.tax_rate=Decimal('7.50');company.save()
    order=place(catalog,payload);line=order.lines.get()
    assert line.tax_total==Decimal('225') and order.grand_total==Decimal('3315')
    company.tax_rate=Decimal('20');company.save()
    services.order_action(order.id,'prepare',{},admin);order.refresh_from_db()
    assert order.status=='preparing' and order.prepared_at
    deliver(order,admin)
    services.order_action(order.id,'collect_cod',{'amount':'3315','reference':'collected'},admin)
    request=services.request_return(order.id,{'reason':'Size','lines':[{'order_line_id':str(line.id),'quantity':1}]})
    services.return_action(request.id,'approve',{},admin);services.return_action(request.id,'receive',{},admin)
    services.return_action(request.id,'inspect',{'lines':[{'id':str(request.lines.get().id),'accepted_quantity':1,'restock_quantity':1,'disposition':'restock'}]},admin)
    allocation=RefundLine.objects.get(refund__order=order)
    assert allocation.amount==Decimal('1075') and allocation.tax_amount==Decimal('75') and allocation.shipping_amount==0
    assert allocation.amount-allocation.tax_amount-allocation.shipping_amount==Decimal('1000')
    line.refresh_from_db();assert line.tax_total==Decimal('225')

def test_tax_partial_cancellation_then_cod_collection(catalog,payload,admin):
    CompanySettings.objects.filter(pk=1).update(tax_rate='5.00')
    order=place(catalog,payload);line=order.lines.get()
    services.order_action(order.id,'prepare',{},admin)
    services.cancel_order(order.id,admin,[{'order_line_id':str(line.id),'quantity':1}])
    deliver(order,admin)
    services.order_action(order.id,'collect_cod',{'amount':'2190.00','reference':'receipt'},admin)
    assert services.collected(order)==Decimal('2190')

def test_cumulative_rounding_full_paid_cancellation_refunds_exact_cash(catalog,payload,admin):
    sku=catalog[2];sku.price=Decimal('0.05');sku.save()
    CompanySettings.objects.filter(pk=1).update(tax_rate='10.00')
    order=place(catalog,payload);line=order.lines.get()
    # Simulate an independently verified prepaid receipt to exercise cancellation allocations.
    order.payment_method='sslcommerz';order.save()
    payment=order.payments.get();payment.method='sslcommerz';payment.status='successful';payment.collected_at=timezone.now();payment.save()
    for _ in range(3): services.cancel_order(order.id,admin,[{'order_line_id':str(line.id),'quantity':1}])
    allocations=list(RefundLine.objects.filter(refund__order=order))
    assert sum((item.amount for item in allocations),Decimal('0'))==order.grand_total
    assert sum((item.tax_amount for item in allocations),Decimal('0'))==line.tax_total
    assert sum((item.shipping_amount for item in allocations),Decimal('0'))==order.shipping_total

def test_private_company_disallows_sandbox_checkout_and_dispatch(catalog,payload,admin,settings):
    settings.PRODUCTSTAT_DEMO=False;settings.SSLCOMMERZ_STORE_ID='test';settings.SSLCOMMERZ_STORE_PASSWORD='test';settings.SSLCOMMERZ_SANDBOX=True
    from rest_framework.exceptions import APIException
    with pytest.raises(APIException): place(catalog,{**payload,'payment_method':'sslcommerz'})
    assert not Order.objects.exists()
    order=place(catalog,payload);order.payments.update(is_sandbox=True)
    with pytest.raises(ValidationError): services.order_action(order.id,'dispatch',{},admin)
    # Cancellation remains available to release accidentally retained legacy reservations.
    services.cancel_order(order.id,admin)

def test_public_demo_does_not_enqueue_external_email(catalog,payload,settings):
    settings.PRODUCTSTAT_DEMO=True
    order=place(catalog,{**payload,'email':'visitor@example.com'})
    services.notify(order,'Subject','Body')
    assert not OutboxEvent.objects.filter(kind__in=['order_confirmation','order_update']).exists()

def test_database_rejects_impossible_amounts_and_quantities(catalog,payload):
    order=place(catalog,payload);line=order.lines.get()
    with pytest.raises(IntegrityError),transaction.atomic():
        OrderLine.objects.filter(pk=line.pk).update(shipped_quantity=4)
    with pytest.raises(IntegrityError),transaction.atomic():
        Payment.objects.filter(order=order).update(settled_amount=Decimal('999999'))
    with pytest.raises(IntegrityError),transaction.atomic():
        CompanySettings.objects.filter(pk=1).update(tax_rate=Decimal('100.01'))

def test_health_readiness_checks_redis_without_exposing_error(catalog):
    client=APIClient()
    with patch('redis.Redis.ping',return_value=True):
        assert client.get('/api/v1/health/').status_code==200
    with patch('redis.Redis.ping',side_effect=Exception('secret connection string')):
        response=client.get('/api/v1/health/')
        assert response.status_code==503 and 'secret' not in str(response.data)

def test_malformed_operation_payloads_return_validation_errors(catalog,payload,admin):
    order=place(catalog,payload);client=APIClient();client.force_authenticate(admin)
    response=client.post(f'/api/v1/staff/orders/{order.id}/action/',{'action':'cancel','lines':[42]},format='json')
    assert response.status_code==400
    response=client.post('/api/v1/staff/inventory/',{'sku_id':str(catalog[2].id),'delta':'nan','reason':'bad'},format='json')
    assert response.status_code==400

def test_invalid_settings_zone_rolls_back_company_change(catalog,admin):
    client=APIClient();client.force_authenticate(admin)
    original=CompanySettings.objects.get(pk=1).name
    response=client.patch('/api/v1/staff/settings/',{'name':'Should roll back','delivery_zones':[{'id':catalog[0].id,'charge':'-20'}]},format='json')
    assert response.status_code==400
    assert CompanySettings.objects.get(pk=1).name==original

def test_request_id_is_sanitized_and_query_token_not_logged(catalog,payload,caplog):
    order=place(catalog,payload);client=APIClient()
    with caplog.at_level('INFO',logger='productstat.requests'):
        response=client.get(f'/api/v1/orders/{order.id}/?token={services.token_for(order)}',HTTP_X_REQUEST_ID='invalid\trequest-id')
    assert response.status_code==200 and len(response['X-Request-ID'])==36
    assert services.token_for(order) not in caplog.text
    assert 'http_request' in caplog.text

def test_staff_catalog_and_inventory_search_are_paginated(catalog,admin):
    client=APIClient();client.force_authenticate(admin)
    response=client.get('/api/v1/staff/products/?q=BAG-01&page=1&page_size=1')
    assert response.status_code==200 and response.data['count']==1 and len(response.data['results'])==1
    response=client.get('/api/v1/staff/inventory/?q=BAG-01&page=2&page_size=1')
    assert response.status_code==200 and response.data['count']==1 and response.data['results']==[]

@pytest.mark.django_db(transaction=True)
def test_first_concurrent_api_checkout_retries_share_session_identity(catalog,payload,monkeypatch):
    """Both first checkout requests load the cart before either response saves it."""
    original=APIClient()
    original.get('/api/v1/bootstrap/')
    original.post('/api/v1/cart/',{'sku_id':str(catalog[2].id),'quantity':2},format='json')
    assert 'checkout_identity' not in original.session
    assert original.session.session_key
    cookies={key:value.value for key,value in original.cookies.items()}
    barrier=Barrier(2)
    real_checkout=services.checkout
    def synchronized_checkout(*args,**kwargs):
        barrier.wait(timeout=10)
        return real_checkout(*args,**kwargs)
    monkeypatch.setattr(services,'checkout',synchronized_checkout)
    def submit(_):
        close_old_connections()
        try:
            client=APIClient()
            for key,value in cookies.items(): client.cookies[key]=value
            response=client.post('/api/v1/checkout/',payload,format='json',HTTP_IDEMPOTENCY_KEY='first-concurrent-api-key')
            return response.status_code,response.json()
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(submit,range(2)))
    assert sorted(status for status,_ in responses)==[200,201]
    assert responses[0][1]['order']['id']==responses[1][1]['order']['id']
    assert responses[0][1]['access_token']==responses[1][1]['access_token']
    assert Order.objects.count()==1
    sku=catalog[2];sku.refresh_from_db();assert sku.reserved==2
