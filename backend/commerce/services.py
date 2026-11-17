"""Transactional commerce operations. Imported history never invokes these services."""
import hashlib
import hmac
import json
import secrets
from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo
from django.conf import settings
from django.db import connection, transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from .models import (AuditEvent,CompanySettings,DeliveryZone,Order,OrderLine,OutboxEvent,Payment,PaymentSettlement,Refund,RefundLine,ReturnRequest,ReturnLine,Shipment,ShipmentLine,SKU,StockMovement)

def money(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0 or result > Decimal('9999999999.99'):
            raise InvalidOperation
        return result.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError('Invalid nonnegative money amount.')

def integer(value, minimum=1, maximum=10000):
    if isinstance(value,bool):
        raise ValidationError('Quantity must be an integer.')
    try:
        result = int(value)
        if str(result) != str(value) or not minimum <= result <= maximum:
            raise ValueError
        return result
    except (TypeError,ValueError):
        raise ValidationError(f'Quantity must be an integer between {minimum} and {maximum}.')

def audit(actor,event,entity,reference,details=None):
    AuditEvent.objects.create(actor=actor if actor and actor.is_authenticated else None,event=event,entity=entity,reference=str(reference),details=details or {})

def token_for(order):
    return hmac.new(settings.SECRET_KEY.encode(),f'order:{order.id}'.encode(),hashlib.sha256).hexdigest()

def token_matches(order, token):
    return bool(token) and bool(order.guest_token_hash) and secrets.compare_digest(hashlib.sha256(str(token).encode()).hexdigest(),order.guest_token_hash)

def notify(order,subject,body,kind='order_update'):
    if order.email and not settings.PRODUCTSTAT_DEMO:
        OutboxEvent.objects.create(kind=kind,payload={'to':order.email,'subject':subject,'body':body,'order_id':str(order.id)})

def move_stock(sku,on_hand_delta=0,reserved_delta=0,kind='adjustment',reference='',actor=None):
    """Caller holds the SKU row lock and the surrounding transaction."""
    if sku.on_hand + on_hand_delta < 0 or sku.reserved + reserved_delta < 0 or sku.on_hand + on_hand_delta < sku.reserved + reserved_delta:
        raise ValidationError(f'Insufficient available stock for {sku.code}.')
    sku.on_hand += on_hand_delta
    sku.reserved += reserved_delta
    sku.save(update_fields=['on_hand','reserved'])
    StockMovement.objects.create(sku=sku,on_hand_delta=on_hand_delta,reserved_delta=reserved_delta,kind=kind,reference=str(reference),actor=actor if actor and actor.is_authenticated else None)

@transaction.atomic
def adjust_stock(sku_id,delta,reason,actor):
    if not reason or not str(reason).strip():
        raise ValidationError('An adjustment reason is required.')
    delta = integer(delta,minimum=-1000000,maximum=1000000)
    sku = SKU.objects.select_for_update().get(pk=sku_id)
    move_stock(sku,on_hand_delta=delta,kind='adjustment',reference=reason,actor=actor)
    audit(actor,'stock_adjusted','sku',sku.id,{'delta':delta,'reason':reason})
    return sku

def advisory_lock(value):
    if connection.vendor == 'postgresql':
        signed = int.from_bytes(hashlib.sha256(value.encode()).digest()[:8],'big',signed=True)
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s)',[signed])

@transaction.atomic
def checkout(cart,data,key,identity,user=None):
    if not key or len(key) > 100:
        raise ValidationError('A unique Idempotency-Key header of at most 100 characters is required.')
    fingerprint = hashlib.sha256(json.dumps({'identity':identity,'user_id':user.pk if user and user.is_authenticated else None,'data':data},sort_keys=True).encode()).hexdigest()
    advisory_lock('checkout:'+key)
    existing = Order.objects.filter(idempotency_key=key).first()
    if existing:
        if existing.checkout_fingerprint != fingerprint:
            raise ValidationError('This idempotency key was already used with a different checkout.')
        if cart:
            expected={str(line.sku_id):line.quantity for line in existing.lines.all()}
            submitted={str(sku_id):integer(quantity,maximum=100) for sku_id,quantity in cart.items()}
            if submitted!=expected:
                raise ValidationError('This idempotency key was already used with different cart contents. Use a new key for a new checkout.')
        return existing,False
    if not cart:
        raise ValidationError('Your cart is empty.')
    method = data.get('payment_method')
    company,_ = CompanySettings.objects.get_or_create(pk=1)
    if method not in ['cod','sslcommerz'] or method == 'cod' and not company.cod_enabled:
        raise ValidationError('This payment method is unavailable.')
    if method == 'sslcommerz' and (not (settings.SSLCOMMERZ_STORE_ID and settings.SSLCOMMERZ_STORE_PASSWORD) or settings.SSLCOMMERZ_SANDBOX and not settings.PRODUCTSTAT_DEMO):
        from rest_framework.exceptions import APIException
        exc = APIException('Online payment is not configured for this company. Sandbox payments are restricted to the demo. Choose cash on delivery.'); exc.status_code=503
        raise exc
    zone = DeliveryZone.objects.filter(pk=data.get('delivery_zone_id'),is_active=True).first()
    if not zone:
        raise ValidationError('Choose a valid delivery zone.')
    skus = list(SKU.objects.select_for_update(of=('self',)).select_related('product').filter(pk__in=cart.keys()).order_by('id'))
    if len(skus) != len(cart):
        raise ValidationError('A cart product is no longer available.')
    now = timezone.now()
    order = Order.objects.create(number='PS-'+now.strftime('%y%m%d')+'-'+secrets.token_hex(4).upper(),user=user if user and user.is_authenticated else None,customer_name=data['customer_name'],email=data['email'],phone=data['phone'],address=data['address'],status='confirmed' if method=='cod' else 'pending_payment',payment_method=method,shipping_total=zone.charge,confirmed_at=now if method=='cod' else None,reservation_expires_at=now+timedelta(minutes=15) if method=='sslcommerz' else None,idempotency_key=key,checkout_fingerprint=fingerprint)
    subtotal = Decimal('0'); tax_total = Decimal('0')
    for sku in skus:
        quantity = integer(cart[str(sku.id)],maximum=100)
        if not sku.is_active or not sku.product.is_active or sku.available < quantity:
            raise ValidationError(f'{sku.product.name} / {sku.label or sku.code} has insufficient available stock.')
        line_tax=money(sku.price*quantity*company.tax_rate/100)
        OrderLine.objects.create(order=order,sku=sku,sku_code=sku.code,product_name=sku.product.name,variant_name=sku.label,quantity=quantity,unit_price=sku.price,tax_total=line_tax)
        move_stock(sku,reserved_delta=quantity,kind='reserve',reference=order.id,actor=user)
        subtotal += sku.price * quantity
        tax_total += line_tax
    order.subtotal = subtotal
    order.tax_total=tax_total
    order.grand_total = subtotal + zone.charge + tax_total
    if order.grand_total>Decimal('999999999999.99'):
        raise ValidationError('The order exceeds the supported monetary limit.')
    order.guest_token_hash = hashlib.sha256(token_for(order).encode()).hexdigest()
    order.save()
    Payment.objects.create(order=order,method=method,amount=order.grand_total,is_sandbox=method=='sslcommerz' and settings.SSLCOMMERZ_SANDBOX,provider_transaction_id='PS'+order.id.hex if method=='sslcommerz' else None)
    audit(user,'order_created','order',order.id,{'payment_method':method})
    notify(order,'Order received: '+order.number,'Your order '+order.number+' was received. We will update you as fulfillment progresses.','order_confirmation')
    return order,True

def ensure_live(order):
    if order.is_historical:
        raise ValidationError('Historical imports are read-only and cannot trigger commerce operations.')

def collected(order):
    return order.payments.filter(status__in=['successful','exception']).aggregate(total=Sum('amount'))['total'] or Decimal('0')

def owed_refunds(order):
    return order.refunds.aggregate(total=Sum('amount'))['total'] or Decimal('0')

def prorate(total,quantity,ordered_quantity,previous=0):
    """Cumulative rounding ensures repeated partial actions never create extra paisa."""
    return money(total*(previous+quantity)/ordered_quantity)-money(total*previous/ordered_quantity)

def line_allocation(line,quantity,previous=0):
    merchandise=prorate(line.unit_price*line.quantity-line.discount_total,quantity,line.quantity,previous)
    tax=prorate(line.tax_total,quantity,line.quantity,previous)
    return (line,merchandise,tax,Decimal('0'))

def create_refund(order,allocations,reason,return_request=None):
    allocations=[tuple(item) if len(item)==4 else (item[0],item[1],Decimal('0'),Decimal('0')) for item in allocations]
    amount = sum((merchandise+tax+shipping for _,merchandise,tax,shipping in allocations),Decimal('0')).quantize(Decimal('.01'))
    remaining = collected(order) - owed_refunds(order)
    if amount <= 0 or remaining <= 0:
        return None
    # Refunds cannot exceed actual cash received. Uncollected COD returns reduce receivables.
    amount = min(amount,remaining)
    refund = Refund.objects.create(order=order,return_request=return_request,amount=amount,reason=reason)
    remaining_amount = amount
    for line,merchandise,tax,shipping in allocations:
        value=merchandise+tax+shipping
        part=min(money(value),remaining_amount)
        if part > 0:
            ratio=part/value
            tax_part=min(money(tax*ratio),part)
            shipping_part=min(money(shipping*ratio),part-tax_part)
            RefundLine.objects.create(refund=refund,order_line=line,amount=part,tax_amount=tax_part,shipping_amount=shipping_part)
            remaining_amount -= part
    return refund

def _cancel_locked(order,actor=None,requested_lines=None,expired=False):
    ensure_live(order)
    if order.status not in ['pending_payment','confirmed','preparing']:
        if order.status=='cancelled' and requested_lines is None:
            return order
        raise ValidationError('Only undispatched orders can be cancelled.')
    lines = list(order.lines.select_for_update().order_by('sku_id'))
    requests = None
    if requested_lines is not None:
        if not isinstance(requested_lines,list) or not requested_lines:
            raise ValidationError('Choose at least one order line.')
        requests = {}
        for item in requested_lines:
            if item.get('order_line_id') in requests:
                raise ValidationError('Duplicate order line.')
            requests[item.get('order_line_id')] = integer(item.get('quantity'))
        if set(requests)-{str(line.id) for line in lines}:
            raise ValidationError('Unknown order line.')
    allocations = []
    for line in lines:
        quantity = requests.get(str(line.id),0) if requests is not None else line.quantity-line.cancelled_quantity
        if quantity > line.quantity-line.cancelled_quantity:
            raise ValidationError('Cancellation exceeds remaining quantity.')
        if quantity:
            sku = SKU.objects.select_for_update().get(pk=line.sku_id)
            move_stock(sku,reserved_delta=-quantity,kind='reservation_expired' if expired else 'cancel',reference=order.id,actor=actor)
            allocations.append(line_allocation(line,quantity,line.cancelled_quantity))
            line.cancelled_quantity += quantity; line.save(update_fields=['cancelled_quantity'])
    if all(line.cancelled_quantity == line.quantity for line in lines):
        order.status='cancelled';order.cancelled_at=timezone.now();order.reservation_expires_at=None;order.save()
        if collected(order)>owed_refunds(order):
            # Line allocations already include snapshotted tax; full cancellation also refunds shipping.
            if allocations:
                line,merchandise,tax,shipping=allocations[-1]
                allocations[-1]=(line,merchandise,tax,shipping+order.shipping_total)
    elif order.payment_method=='sslcommerz' and order.status=='pending_payment':
        raise ValidationError('Pending online-payment orders must be cancelled in full.')
    create_refund(order,allocations,'Cancelled merchandise')
    audit(actor,'order_cancelled','order',order.id,{'expired':expired})
    notify(order,'Order cancellation: '+order.number,'Your cancellation was recorded. Refunds, where applicable, are tracked separately.')
    return order

@transaction.atomic
def cancel_order(order_id,actor=None,lines=None):
    return _cancel_locked(Order.objects.select_for_update().get(pk=order_id),actor,lines)

def expire_reservations():
    count = 0
    ids = list(Order.objects.filter(is_historical=False,status='pending_payment',reservation_expires_at__lte=timezone.now()).values_list('id',flat=True))
    for order_id in ids:
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=order_id)
            if order.status=='pending_payment' and order.reservation_expires_at and order.reservation_expires_at<=timezone.now():
                _cancel_locked(order,expired=True); count += 1
    return count

@transaction.atomic
def order_action(order_id,action,data,actor):
    order = Order.objects.select_for_update().get(pk=order_id)
    ensure_live(order)
    if action in ['prepare','dispatch'] and not settings.PRODUCTSTAT_DEMO and order.payments.filter(is_sandbox=True).exists():
        raise ValidationError('Sandbox payments cannot authorize real-company fulfillment.')
    now = timezone.now()
    if action=='cancel':
        return _cancel_locked(order,actor,data.get('lines'))
    if action=='prepare':
        if order.status!='confirmed': raise ValidationError('Only confirmed orders can be prepared.')
        order.status='preparing';order.prepared_at=now
    elif action=='dispatch':
        if order.status not in ['confirmed','preparing']: raise ValidationError('Only confirmed or preparing orders can be dispatched.')
        shipment = Shipment.objects.create(order=order,state='dispatched',tracking_number=str(data.get('tracking_number',''))[:120],carrier=str(data.get('carrier',''))[:100],dispatched_at=now)
        for line in order.lines.select_for_update().order_by('sku_id'):
            quantity = line.quantity-line.cancelled_quantity
            if not quantity: continue
            sku = SKU.objects.select_for_update().get(pk=line.sku_id)
            move_stock(sku,on_hand_delta=-quantity,reserved_delta=-quantity,kind='dispatch',reference=order.id,actor=actor)
            ShipmentLine.objects.create(shipment=shipment,order_line=line,quantity=quantity)
            line.shipped_quantity=quantity;line.save(update_fields=['shipped_quantity'])
        order.status='dispatched';order.dispatched_at=now
    elif action in ['deliver','fail','return_to_origin']:
        if order.status!='dispatched' and not (action=='return_to_origin' and order.status=='failed'):
            raise ValidationError('This shipment cannot receive that outcome.')
        shipment = order.shipments.select_for_update().latest('dispatched_at')
        shipment.state={'deliver':'delivered','fail':'failed','return_to_origin':'returned_to_origin'}[action]
        shipment.completed_at=now
        if action=='deliver':
            shipment.delivered_at=now;order.delivered_at=now
            for line in order.lines.all():
                line.delivered_quantity=line.shipped_quantity;line.delivered_at=now;line.save(update_fields=['delivered_quantity','delivered_at'])
        # Returned-to-origin inventory remains quarantined until an explicit staff stock adjustment.
        shipment.save();order.status=shipment.state
        if action=='return_to_origin':
            create_refund(order,[line_allocation(line,line.quantity-line.cancelled_quantity,line.cancelled_quantity) for line in order.lines.all()],'Undelivered return to origin')
    elif action in ['collect_cod','settle_cod']:
        if order.payment_method!='cod': raise ValidationError('This order is not cash on delivery.')
        payment=order.payments.select_for_update().get(method='cod')
        amount=money(data.get('amount'))
        if not str(data.get('reference','')).strip(): raise ValidationError('A collection/settlement reference is required.')
        if action=='collect_cod':
            if order.status!='delivered' or payment.status=='successful': raise ValidationError('Collection requires an uncollected delivered order.')
            due=order.grand_total-sum((sum(line_allocation(line,line.cancelled_quantity+line.returned_quantity)[1:]) for line in order.lines.all()),Decimal('0'))
            if amount!=due: raise ValidationError(f'The expected COD collection is {due:.2f}.')
            payment.amount=amount;payment.status='successful';payment.collected_at=now
        else:
            reference=str(data.get('reference','')).strip()
            if len(reference)>200: raise ValidationError('Settlement reference must be at most 200 characters.')
            previous=payment.settlements.filter(reference=reference).first()
            if previous:
                if previous.amount!=amount:
                    raise ValidationError('This settlement reference was already used with a different amount.')
                return order
            if payment.status!='successful' or amount<=0 or payment.settled_amount+amount>payment.amount:
                raise ValidationError('Settlement must be positive and cannot exceed collected cash.')
            PaymentSettlement.objects.create(payment=payment,amount=amount,settled_at=now,reference=reference,actor=actor,source='live')
            payment.settled_amount+=amount;payment.settled_at=now
        payment.save()
    else:
        raise ValidationError('Unknown order action.')
    order.save()
    audit(actor,action,'order',order.id,{'reference':str(data.get('reference','')),'amount':str(data.get('amount',''))})
    if action not in ['collect_cod','settle_cod']:
        notify(order,'Order update: '+order.number,'Your order status is now '+order.status.replace('_',' ')+'.')
    return order

@transaction.atomic
def request_return(order_id,data,actor=None):
    order=Order.objects.select_for_update().get(pk=order_id);ensure_live(order)
    if order.status!='delivered' or not order.delivered_at: raise ValidationError('Only delivered merchandise can be returned.')
    company,_=CompanySettings.objects.get_or_create(pk=1)
    business_tz=ZoneInfo('Asia/Dhaka')
    last_return_date=timezone.localdate(order.delivered_at,business_tz)+timedelta(days=company.return_window_days)
    if timezone.localdate(timezone.now(),business_tz)>last_return_date: raise ValidationError('The return-request window has closed. Contact support for exceptions.')
    if not str(data.get('reason','')).strip(): raise ValidationError('A return reason is required.')
    entries=data.get('lines')
    if not isinstance(entries,list) or not entries: raise ValidationError('Choose at least one return line.')
    request=ReturnRequest.objects.create(order=order,reason=data['reason'])
    seen=set()
    for item in entries:
        line=order.lines.filter(pk=item.get('order_line_id')).first()
        if not line or line.id in seen: raise ValidationError('Invalid or duplicated return line.')
        seen.add(line.id);quantity=integer(item.get('quantity'))
        pending=line.return_lines.exclude(return_request__status__in=['rejected','inspected']).aggregate(total=Sum('quantity'))['total'] or 0
        if quantity>line.delivered_quantity-line.returned_quantity-pending: raise ValidationError('Return quantity exceeds eligible delivered merchandise.')
        ReturnLine.objects.create(return_request=request,order_line=line,quantity=quantity)
    audit(actor,'return_requested','return',request.id)
    return request

@transaction.atomic
def return_action(request_id,action,data,actor):
    # Lock order before return so lock ordering agrees with order operations.
    request_ref=ReturnRequest.objects.get(pk=request_id)
    order=Order.objects.select_for_update().get(pk=request_ref.order_id);ensure_live(order)
    request=ReturnRequest.objects.select_for_update().get(pk=request_id)
    transitions={'approve':('requested','approved'),'reject':('requested','rejected'),'receive':('approved','received'),'inspect':('received','inspected')}
    if action not in transitions or request.status!=transitions[action][0]: raise ValidationError('Invalid return transition.')
    now=timezone.now()
    if action=='receive': request.received_at=now
    if action=='inspect':
        entries=data.get('lines',[])
        if not isinstance(entries,list): raise ValidationError('Inspection lines are required.')
        values={str(item.get('id')):item for item in entries}
        lines=list(request.lines.select_related('order_line').order_by('order_line__sku_id'))
        if len(values)!=len(entries) or set(values)!={str(line.id) for line in lines}: raise ValidationError('Inspect every return line exactly once.')
        allocations=[]
        for line in lines:
            item=values[str(line.id)]
            accepted=integer(item.get('accepted_quantity'),minimum=0,maximum=line.quantity)
            restock=integer(item.get('restock_quantity',0),minimum=0,maximum=accepted)
            disposition=item.get('disposition','quarantine')
            if disposition not in ['restock','quarantine','dispose'] or (restock and disposition!='restock'): raise ValidationError('Invalid restock disposition.')
            order_line=OrderLine.objects.select_for_update().get(pk=line.order_line_id)
            if order_line.returned_quantity+accepted>order_line.delivered_quantity: raise ValidationError('Accepted returns exceed delivery.')
            line.accepted_quantity=accepted;line.restock_quantity=restock;line.disposition=disposition;line.save()
            allocations.append(line_allocation(order_line,accepted,order_line.cancelled_quantity+order_line.returned_quantity))
            order_line.returned_quantity+=accepted;order_line.returned_at=now;order_line.save(update_fields=['returned_quantity','returned_at'])
            if restock:
                sku=SKU.objects.select_for_update().get(pk=order_line.sku_id)
                move_stock(sku,on_hand_delta=restock,kind='return_restock',reference=request.id,actor=actor)
        create_refund(order,allocations,'Accepted returned merchandise',request)
        request.inspected_at=now
    request.status=transitions[action][1];request.save()
    audit(actor,'return_'+action,'return',request.id)
    notify(order,'Return update: '+order.number,'Your return request is now '+request.status+'.','return_update')
    return request

@transaction.atomic
def confirm_refund(refund_id,reference,actor):
    refund_ref=Refund.objects.get(pk=refund_id)
    order=Order.objects.select_for_update().get(pk=refund_ref.order_id)
    refund=Refund.objects.select_for_update().get(pk=refund_id)
    ensure_live(order)
    if not str(reference or '').strip(): raise ValidationError('An external refund transaction reference is required.')
    if refund.status=='confirmed':
        if refund.reference!=reference: raise ValidationError('Refund already confirmed with another reference.')
        return refund
    confirmed=order.refunds.filter(status='confirmed').aggregate(total=Sum('amount'))['total'] or Decimal('0')
    if confirmed+refund.amount>collected(order): raise ValidationError('Refunds exceed collected cash.')
    refund.reference=reference;refund.status='confirmed';refund.confirmed_at=timezone.now();refund.save()
    audit(actor,'refund_confirmed','refund',refund.id,{'reference':reference,'amount':str(refund.amount)})
    return refund
