"""SSLCOMMERZ server-to-server initiation and independently validated callbacks."""
from decimal import Decimal, InvalidOperation
import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError
from .models import Order,Payment
from .services import _cancel_locked,audit,collected,create_refund,notify,line_allocation

class GatewayUnavailable(APIException):
    status_code=503
    default_detail='The payment gateway is unavailable. Your order remains pending; retry or choose a new COD order after cancellation.'

def base_url():
    return 'https://sandbox.sslcommerz.com' if settings.SSLCOMMERZ_SANDBOX else 'https://securepay.sslcommerz.com'

@transaction.atomic
def initiate(order):
    payment=Payment.objects.select_for_update().get(order=order,method='sslcommerz')
    if payment.is_sandbox and not settings.PRODUCTSTAT_DEMO:
        raise GatewayUnavailable('Sandbox payments are disabled for real-company orders.')
    if payment.gateway_url:
        return payment.gateway_url
    if order.status!='pending_payment':
        raise ValidationError('This order is no longer awaiting payment.')
    callback=settings.PUBLIC_BASE_URL+'/api/v1/payments/sslcommerz/'
    payload={'store_id':settings.SSLCOMMERZ_STORE_ID,'store_passwd':settings.SSLCOMMERZ_STORE_PASSWORD,'total_amount':str(payment.amount),'currency':'BDT','tran_id':payment.provider_transaction_id,'success_url':callback+'return/','fail_url':callback+'return/','cancel_url':callback+'return/','ipn_url':callback+'ipn/','cus_name':order.customer_name,'cus_email':order.email or 'guest@example.invalid','cus_add1':order.address.get('line1',''),'cus_city':order.address.get('city',''),'cus_country':'Bangladesh','cus_phone':order.phone,'shipping_method':'YES','ship_name':order.customer_name,'ship_add1':order.address.get('line1',''),'ship_city':order.address.get('city',''),'ship_country':'Bangladesh','ship_postcode':order.address.get('postal_code','0000'),'product_name':'Order '+order.number,'product_category':'Physical goods','product_profile':'physical-goods','num_of_item':sum(line.quantity for line in order.lines.all())}
    try:
        response=requests.post(base_url()+'/gwprocess/v4/api.php',data=payload,timeout=15)
        response.raise_for_status();data=response.json()
        url=data.get('GatewayPageURL','')
        if data.get('status')!='SUCCESS' or not url.startswith(base_url()+'/'):
            raise GatewayUnavailable()
    except (requests.RequestException,ValueError):
        raise GatewayUnavailable()
    # The provider transaction identifier is stable across client retries.
    payment.gateway_url=url;payment.save(update_fields=['gateway_url'])
    audit(None,'payment_initiated','order',order.id,{'sandbox':payment.is_sandbox})
    return url

def validate_callback(data):
    transaction_id=str(data.get('tran_id',''))
    validation_id=str(data.get('val_id',''))
    if not transaction_id or not validation_id:
        raise ValidationError('A transaction and provider validation ID are required.')
    reference=Payment.objects.filter(provider_transaction_id=transaction_id,method='sslcommerz').first()
    if not reference:
        raise ValidationError('Unknown transaction.')
    if reference.is_sandbox and not settings.PRODUCTSTAT_DEMO:
        raise ValidationError('Sandbox verification cannot authorize real-company orders.')
    try:
        response=requests.get(base_url()+'/validator/api/validationserverAPI.php',params={'val_id':validation_id,'store_id':settings.SSLCOMMERZ_STORE_ID,'store_passwd':settings.SSLCOMMERZ_STORE_PASSWORD,'format':'json'},timeout=15)
        response.raise_for_status();validated=response.json()
    except (requests.RequestException,ValueError):
        raise GatewayUnavailable('Provider verification failed; no payment state was changed.')
    if validated.get('status') not in ['VALID','VALIDATED'] or validated.get('tran_id')!=transaction_id or validated.get('currency')!='BDT':
        raise ValidationError('Provider payment verification did not match this transaction.')
    try:
        amount=Decimal(str(validated['amount']))
        if not amount.is_finite(): raise InvalidOperation
    except (InvalidOperation,KeyError):
        raise ValidationError('Invalid verified payment amount.')
    with transaction.atomic():
        order=Order.objects.select_for_update().get(pk=reference.order_id)
        payment=Payment.objects.select_for_update().get(pk=reference.pk)
        if amount!=payment.amount:
            raise ValidationError('Verified payment amount does not match the order.')
        if payment.status in ['successful','exception']:
            return order
        now=timezone.now()
        if order.status=='pending_payment' and order.reservation_expires_at and now>=order.reservation_expires_at:
            _cancel_locked(order,expired=True)
        payment.collected_at=now;payment.provider_validation_id=validation_id
        if order.status=='pending_payment':
            payment.status='successful'
            order.status='confirmed';order.confirmed_at=now;order.reservation_expires_at=None;order.save()
        else:
            payment.status='exception'
        payment.save()
        if payment.status=='exception':
            # Captured funds on an expired order are an obligation, never automatic fulfillment.
            lines=list(order.lines.all())
            if lines:
                allocations=[line_allocation(line,line.quantity) for line in lines]
                line,merchandise,tax,shipping=allocations[-1]
                allocations[-1]=(line,merchandise,tax,shipping+order.shipping_total)
                create_refund(order,allocations,'Late payment on cancelled order')
        audit(None,'payment_verified','order',order.id,{'status':payment.status,'amount':str(amount)})
        notify(order,'Payment update: '+order.number,'Your payment was verified. Order status: '+order.status+'.')
        return order
