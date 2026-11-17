"""Paisa-exact agreement between stock/refund allocation and every report surface."""
import csv
from datetime import datetime
from decimal import Decimal
import io
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo
import pytest
from rest_framework.test import APIClient
from commerce.models import Order,OrderLine,Payment,Product,ReturnLine,ReturnRequest,Shipment,ShipmentLine,SKU,User
from commerce.reporting import analytics,drilldown,filters_from_params,variant_analytics
from commerce.reporting_money import allocate_events,money,prorate
from commerce.services import cancel_order,line_allocation

TZ=ZoneInfo('Asia/Dhaka')
def at(value): return datetime.fromisoformat(value).replace(tzinfo=TZ)

def make_line(quantity=3,price='100.00',discount='0.01',cancelled=0,returned=0):
    product=Product.objects.create(name='Synthetic allocation fixture',slug='allocation-'+uuid4().hex,category='Tests')
    sku=SKU.objects.create(product=product,code='PENNY-'+uuid4().hex[:12],price=price)
    order=Order.objects.create(number='PENNY-'+uuid4().hex[:12],customer_name='Synthetic',is_historical=True,created_at=at('2026-01-01T12:00:00'))
    line=OrderLine.objects.create(order=order,sku=sku,sku_code=sku.code,product_name=product.name,quantity=quantity,unit_price=price,discount_total=discount,cancelled_quantity=cancelled,shipped_quantity=quantity-cancelled,delivered_quantity=quantity-cancelled,returned_quantity=returned)
    line.refresh_from_db()
    return product,sku,order,line

def delivery(order,line,value,quantity=1,event_id=None):
    timestamp=at(value)
    shipment=Shipment.objects.create(order=order,state='delivered',dispatched_at=order.created_at,delivered_at=timestamp,completed_at=timestamp)
    values={'shipment':shipment,'order_line':line,'quantity':quantity}
    if event_id is not None: values['id']=event_id
    return ShipmentLine.objects.create(**values)

def accepted_return(order,line,value,quantity=1):
    returned=ReturnRequest.objects.create(order=order,status='inspected',reason='Size or preference',inspected_at=at(value))
    return ReturnLine.objects.create(return_request=returned,order_line=line,quantity=quantity,accepted_quantity=quantity)

def assert_surfaces(product,start,end,metric,summary_field,expected):
    filters=filters_from_params({'start':start,'end':end,'product_ids':str(product.id)})
    report=analytics(filters)
    rows=drilldown(filters,metric)
    total=Decimal(expected)
    assert Decimal(report['summary'][summary_field])==total
    assert sum((Decimal(item[summary_field]) for item in report['trend']),Decimal('0'))==total
    assert sum((Decimal(item[summary_field]) for item in report['products']),Decimal('0'))==total
    variants=variant_analytics(product.id,filters)['results']
    assert sum((Decimal(item[summary_field]) for item in variants),Decimal('0'))==total
    assert sum((Decimal(row['value']) for row in rows),Decimal('0'))==total
    user=User.objects.create_user(username='penny-reader-'+uuid4().hex[:10],role='analyst')
    client=APIClient();client.force_authenticate(user)
    response=client.get(f'/api/v1/analytics/export/?metric={metric}&start={start}&end={end}&product_ids={product.id}')
    assert response.status_code==200
    exported=list(csv.DictReader(io.StringIO(response.content.decode())))
    assert sum((Decimal(row['value']) for row in exported),Decimal('0'))==total
    return report,sorted(rows,key=lambda row:(row['event_at'],row['id']))

def test_helper_matches_core_cumulative_rounding_and_half_paisa():
    line=OrderLine(quantity=3,unit_price=Decimal('100'),discount_total=Decimal('.01'),tax_total=Decimal('0'))
    expected=[line_allocation(line,1,previous)[1] for previous in (0,1,2)]
    assert expected==[Decimal('100.00'),Decimal('99.99'),Decimal('100.00')]
    assert [prorate(Decimal('299.99'),1,3,previous) for previous in (0,1,2)]==expected
    assert [prorate(Decimal('.01'),1,2,previous) for previous in (0,1)]==[Decimal('.01'),Decimal('0')]
    assert money(Decimal('.005'))=='0.01' and money(Decimal('-.005'))=='-0.01'

def test_helper_orders_ties_as_text_and_unknown_dates_last():
    timestamp=at('2026-01-01T12:00:00')
    allocated=allocate_events(Decimal('.01'),2,0,[('2',timestamp,1),('10',timestamp,1)])
    assert allocated=={'10':Decimal('.01'),'2':Decimal('0')}
    allocated=allocate_events(Decimal('299.99'),3,0,[('undated',None,1),('b',timestamp,1),('a',timestamp,1)])
    assert allocated=={'a':Decimal('100'),'b':Decimal('99.99'),'undated':Decimal('100')}

@pytest.mark.django_db
def test_split_deliveries_and_cross_period_reports_preserve_all_paisa():
    product,_,order,line=make_line()
    for value in ['2026-01-31T12:00:00','2026-02-01T12:00:00','2026-02-02T12:00:00']: delivery(order,line,value)
    _,rows=assert_surfaces(product,'2026-01-01','2026-02-28','delivered_units','delivered_value','299.99')
    assert [row['value'] for row in rows]==['100.00','99.99','100.00']
    _,february=assert_surfaces(product,'2026-02-01','2026-02-28','delivered_units','delivered_value','199.99')
    assert [row['value'] for row in february]==['99.99','100.00']

@pytest.mark.django_db
def test_cancellation_base_offset_and_accepted_return_match_core_allocations():
    product,_,order,line=make_line(cancelled=1,returned=1)
    delivery(order,line,'2026-01-31T12:00:00');delivery(order,line,'2026-02-01T12:00:00')
    accepted_return(order,line,'2026-02-02T12:00:00')
    report,rows=assert_surfaces(product,'2026-01-01','2026-02-28','delivered_units','delivered_value','199.99')
    assert [row['value'] for row in rows]==['99.99','100.00']
    assert Decimal(report['summary']['net_delivered_value'])==Decimal('100.00')
    _,returns=assert_surfaces(product,'2026-01-01','2026-02-28','returned_units','returned_value','99.99')
    assert Decimal(returns[0]['value'])==line_allocation(line,1,1)[1]
    february,_=assert_surfaces(product,'2026-02-01','2026-02-28','delivered_units','delivered_value','100.00')
    assert february['summary']['net_delivered_value']=='0.01'

@pytest.mark.django_db
def test_split_partial_returns_retain_earlier_period_offset():
    product,_,order,line=make_line(returned=3)
    delivery(order,line,'2026-01-02T12:00:00',quantity=3)
    for value in ['2026-01-31T12:00:00','2026-02-01T12:00:00','2026-02-02T12:00:00']: accepted_return(order,line,value)
    _,rows=assert_surfaces(product,'2026-01-01','2026-02-28','returned_units','returned_value','299.99')
    assert [row['value'] for row in rows]==['100.00','99.99','100.00']
    _,rows=assert_surfaces(product,'2026-02-01','2026-02-28','returned_units','returned_value','199.99')
    assert [row['value'] for row in rows]==['99.99','100.00']

@pytest.mark.django_db
def test_half_paisa_and_equal_timestamp_order_match_sql_and_export():
    product,_,order,line=make_line(quantity=2,price='.01',discount='.01')
    delivery(order,line,'2026-01-02T12:00:00',event_id=2)
    delivery(order,line,'2026-01-02T12:00:00',event_id=10)
    _,rows=assert_surfaces(product,'2026-01-01','2026-01-31','delivered_units','delivered_value','.01')
    assert {row['id']:row['value'] for row in rows}=={'10':'0.01','2':'0.00'}

@pytest.mark.django_db
def test_canonical_partial_cancellation_events_allocate_like_refund_obligations():
    product,sku,order,line=make_line()
    order.is_historical=False;order.status='confirmed';order.payment_method='sslcommerz';order.subtotal=Decimal('300');order.discount_total=Decimal('.01');order.grand_total=Decimal('299.99');order.save()
    line.shipped_quantity=0;line.delivered_quantity=0;line.save()
    sku.on_hand=3;sku.reserved=3;sku.save()
    Payment.objects.create(order=order,method='sslcommerz',status='successful',amount='299.99',collected_at=order.created_at)
    actor=User.objects.create_user(username='cancel-operator',role='operator')
    for value in ['2026-01-31T12:00:00','2026-02-01T12:00:00','2026-02-02T12:00:00']:
        with patch('commerce.services.timezone.now',return_value=at(value)):
            cancel_order(order.id,actor,[{'order_line_id':str(line.id),'quantity':1}])
    filters=filters_from_params({'start':'2026-01-01','end':'2026-02-28','product_ids':str(product.id)})
    rows=sorted(drilldown(filters,'cancelled_units'),key=lambda row:row['event_at'])
    assert [row['value'] for row in rows]==['100.00','99.99','100.00']
    assert sum((Decimal(row['value']) for row in rows),Decimal('0'))==Decimal('299.99')
    assert sum((refund.amount for refund in order.refunds.all()),Decimal('0'))==Decimal('299.99')
    february=filters_from_params({'start':'2026-02-01','end':'2026-02-28','product_ids':str(product.id)})
    assert sum((Decimal(row['value']) for row in drilldown(february,'cancelled_units')),Decimal('0'))==Decimal('199.99')
