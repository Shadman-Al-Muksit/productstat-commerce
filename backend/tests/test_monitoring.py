from datetime import timedelta
from decimal import Decimal
import io
import json
from unittest.mock import patch
import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.cache import caches
from django.core.management import call_command
from django.db import OperationalError
from django.test import RequestFactory
from django.utils import timezone
from rest_framework.request import Request
from rest_framework.test import APIClient
from rest_framework.throttling import AnonRateThrottle
from commerce.models import ImportBatch,Order,OutboxEvent,Payment,Refund,User
from commerce.monitoring import operations_health

pytestmark=pytest.mark.django_db

def order(number,**values):
    return Order.objects.create(number=number,customer_name='Private Customer',email='private@example.com',phone='01799999999',address={'line1':'Private address'},**values)

def test_cod_48_hour_boundary_excludes_history_and_terminal_orders():
    now=timezone.now();boundary=now-timedelta(hours=48)
    flagged=order('BOUNDARY',status='confirmed',confirmed_at=boundary)
    order('PREPARING',status='preparing',confirmed_at=boundary-timedelta(seconds=1))
    order('FRESH',status='confirmed',confirmed_at=boundary+timedelta(seconds=1))
    order('HISTORY',status='confirmed',confirmed_at=boundary,is_historical=True)
    order('DISPATCHED',status='dispatched',confirmed_at=boundary)
    order('PREPAID',status='confirmed',confirmed_at=boundary,payment_method='sslcommerz')
    report=operations_health(now)
    assert report['counts']['overdue_cod_orders']==2
    assert {item['number'] for item in report['overdue_cod_orders']}=={'BOUNDARY','PREPARING'}
    flagged.refresh_from_db();assert flagged.status=='confirmed'
    assert not any(value in json.dumps(report) for value in ['Private Customer','private@example.com','01799999999','Private address'])

def test_exhausted_jobs_include_expired_last_attempt_and_exclude_running_lease():
    now=timezone.now()
    OutboxEvent.objects.create(kind='order_update',status='failed',attempts=8)
    OutboxEvent.objects.create(kind='import_commit',status='processing',attempts=8,next_attempt_at=now-timedelta(seconds=1))
    OutboxEvent.objects.create(kind='order_update',status='processing',attempts=8,next_attempt_at=now+timedelta(minutes=5))
    OutboxEvent.objects.create(kind='order_update',status='failed',attempts=7)
    OutboxEvent.objects.create(kind='order_update',status='sent',attempts=8)
    ImportBatch.objects.create(kind='history',status='failed',filename='private@example.com.csv',source_name='private',errors=[{'message':'private@example.com'}])
    report=operations_health(now)
    assert report['counts']['failed_outbox_jobs']==2 and report['counts']['failed_imports']==1
    assert 'private@example.com' not in json.dumps(report)

def test_refunded_exception_is_resolved_partial_and_multiple_captures_group_by_order():
    unresolved=order('UNRESOLVED')
    Payment.objects.create(order=unresolved,method='sslcommerz',status='exception',amount=60,collected_at=timezone.now())
    Payment.objects.create(order=unresolved,method='sslcommerz',status='exception',amount=40,collected_at=timezone.now())
    Refund.objects.create(order=unresolved,amount=40,status='confirmed',reason='Partial reconciliation')
    resolved=order('RESOLVED')
    Payment.objects.create(order=resolved,method='sslcommerz',status='exception',amount=100,collected_at=timezone.now())
    Refund.objects.create(order=resolved,amount=100,status='confirmed',reason='Reconciled')
    historical=order('OLD-SOURCE',is_historical=True)
    Payment.objects.create(order=historical,method='sslcommerz',status='exception',amount=100)
    report=operations_health()
    assert report['counts']['payment_exceptions']==1
    assert report['payment_exceptions'][0]['number']=='UNRESOLVED'
    assert Decimal(report['payment_exceptions'][0]['unreconciled_amount'])==Decimal('60')

@pytest.mark.parametrize('role,expected',[('administrator',200),('operator',200),('analyst',403),('customer',403)])
def test_operations_endpoint_role_and_no_cache(role,expected):
    user=User.objects.create_user(username=role,role=role)
    client=APIClient();client.force_authenticate(user)
    response=client.get('/api/v1/staff/operations-health/')
    assert response.status_code==expected
    if expected==200:
        assert response['Cache-Control']=='private, no-store'
        assert response.json()['status']=='ok'
    assert APIClient().get('/api/v1/staff/operations-health/').status_code==403

def test_command_outputs_json_and_exit_status_without_notifications():
    clear=io.StringIO();call_command('operations_check',stdout=clear)
    assert json.loads(clear.getvalue())['status']=='ok'
    OutboxEvent.objects.create(kind='order_update',status='failed',attempts=8)
    attention=io.StringIO()
    with pytest.raises(SystemExit) as result: call_command('operations_check',stdout=attention)
    assert result.value.code==1 and json.loads(attention.getvalue())['counts']['failed_outbox_jobs']==1
    unavailable=io.StringIO()
    with patch('commerce.management.commands.operations_check.operations_health',side_effect=OperationalError('secret credentials')):
        with pytest.raises(SystemExit) as result: call_command('operations_check',stdout=unavailable)
    assert result.value.code==2 and 'secret' not in unavailable.getvalue()

def test_two_throttle_instances_share_the_default_cache():
    class OneRequest(AnonRateThrottle):
        rate='1/min';scope='monitoring-test';cache=caches['default']
    request=Request(RequestFactory().get('/test',REMOTE_ADDR='198.51.100.2'));request.user=AnonymousUser()
    assert OneRequest().allow_request(request,None)
    assert not OneRequest().allow_request(request,None)
