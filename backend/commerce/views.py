import secrets
from decimal import Decimal
from django.conf import settings
from django.contrib.auth import authenticate,login,logout,password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction,connection
from django.db.models import Q,Min,Sum,Prefetch
from django.http import HttpResponseRedirect
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view,permission_classes,authentication_classes,throttle_classes
from rest_framework.exceptions import PermissionDenied,ValidationError
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from .models import AuditEvent,CompanySettings,DeliveryZone,Order,Product,SKU,Payment,Refund,ReturnRequest,ReturnLine,User,StockMovement
from .permissions import IsAdministrator,IsOperator,IsStaffReader
from .serializers import CheckoutSerializer,ProductSerializer,ProductWriteSerializer,RegisterSerializer,SettingsSerializer,SKUSerializer,UserSerializer
from .schema import CancelInput,OrderAction,ReturnInput,ReturnAction,RefundInput,InventoryInput
from . import payments,services

class LoginThrottle(AnonRateThrottle):
    scope='login'
    def get_cache_key(self,request,view):
        # An authenticated customer must not bypass account-guessing protection.
        return self.cache_format % {'scope':self.scope,'ident':self.get_ident(request)}
class CheckoutThrottle(AnonRateThrottle):
    scope='checkout'
    def get_cache_key(self,request,view):
        identity='user:'+str(request.user.pk) if request.user.is_authenticated else 'ip:'+self.get_ident(request)
        return self.cache_format % {'scope':self.scope,'ident':identity}

def dt(value): return value.isoformat() if value else None
def user_data(user): return UserSerializer(user).data if user.is_authenticated else None

def return_data(item):
    return {'id':str(item.id),'order_id':str(item.order_id),'order_number':item.order.number,'status':item.status,'reason':item.reason,'created_at':dt(item.created_at),'received_at':dt(item.received_at),'inspected_at':dt(item.inspected_at),'lines':[{'id':str(line.id),'order_line_id':str(line.order_line_id),'product_name':line.order_line.product_name,'quantity':line.quantity,'accepted_quantity':line.accepted_quantity,'restock_quantity':line.restock_quantity,'disposition':line.disposition} for line in item.lines.all()]}

def refund_data(item):
    return {'id':str(item.id),'order_id':str(item.order_id),'order_number':item.order.number,'amount':str(item.amount),'status':item.status,'reason':item.reason,'reference':item.reference,'created_at':dt(item.created_at),'confirmed_at':dt(item.confirmed_at)}

def order_data(order):
    payment_rows=list(order.payments.all())
    order_lines=list(order.lines.all())
    cash=sum((payment.amount for payment in payment_rows if payment.status in ['successful','exception']),Decimal('0'))
    refunds=sum((refund.amount for refund in order.refunds.all() if refund.status=='confirmed'),Decimal('0'))
    reductions=sum((sum(services.line_allocation(line,line.cancelled_quantity+line.returned_quantity)[1:]) for line in order_lines),Decimal('0'))
    amount_due=max(Decimal('0'),order.grand_total-reductions-cash) if order.status not in ['cancelled','failed','returned_to_origin'] else Decimal('0')
    result={'id':str(order.id),'number':order.number,'status':order.status,'payment_method':order.payment_method,'customer_name':order.customer_name,'email':order.email,'phone':order.phone,'address':order.address,'is_historical':order.is_historical,'is_current':order.is_current,'supersedes_id':str(order.supersedes_id) if order.supersedes_id else None,'source':order.source}
    for field in ['subtotal','discount_total','shipping_total','tax_total','grand_total']:
        result[field]=str(getattr(order,field))
    for field in ['created_at','confirmed_at','prepared_at','dispatched_at','delivered_at','reservation_expires_at']:
        result[field]=dt(getattr(order,field))
    result['collected_total']=str(cash);result['refunded_total']=str(refunds)
    result['amount_due']=str(amount_due.quantize(Decimal('.01')))
    result['settled_total']=str(sum((payment.settled_amount for payment in payment_rows),Decimal('0.00')))
    result['lines']=[{'id':str(line.id),'sku_id':str(line.sku_id) if line.sku_id else None,'sku_code':line.sku_code,'product_name':line.product_name,'variant_name':line.variant_name,'quantity':line.quantity,'cancelled_quantity':line.cancelled_quantity,'shipped_quantity':line.shipped_quantity,'delivered_quantity':line.delivered_quantity,'returned_quantity':line.returned_quantity,'unit_price':str(line.unit_price),'discount_total':str(line.discount_total),'tax_total':str(line.tax_total),'line_total':str(line.unit_price*line.quantity-line.discount_total)} for line in order.lines.all()]
    result['shipments']=[{'id':str(shipment.id),'state':shipment.state,'carrier':shipment.carrier,'tracking_number':shipment.tracking_number,'dispatched_at':dt(shipment.dispatched_at),'delivered_at':dt(shipment.delivered_at)} for shipment in order.shipments.all()]
    result['payments']=[{'id':str(payment.id),'method':payment.method,'status':payment.status,'amount':str(payment.amount),'settled_amount':str(payment.settled_amount),'is_sandbox':payment.is_sandbox,'collected_at':dt(payment.collected_at),'settled_at':dt(payment.settled_at)} for payment in order.payments.all()]
    result['returns']=[return_data(item) for item in order.returns.all()]
    result['refunds']=[refund_data(item) for item in order.refunds.all()]
    return result

def order_queryset():
    return Order.objects.prefetch_related('lines','shipments','payments',Prefetch('returns',queryset=ReturnRequest.objects.select_related('order').prefetch_related(Prefetch('lines',queryset=ReturnLine.objects.select_related('order_line')))),Prefetch('refunds',queryset=Refund.objects.select_related('order')))

def page_items(request,queryset,default=25):
    page=services.integer(request.query_params.get('page','1'),maximum=100000)
    size=services.integer(request.query_params.get('page_size',str(default)),maximum=100)
    return page,size,queryset[(page-1)*size:page*size]

def accessible_order(request,pk,staff=False):
    order=get_object_or_404(order_queryset(),pk=pk)
    if staff: return order
    if request.user.is_authenticated and order.user_id==request.user.pk: return order
    token=request.query_params.get('token') or request.headers.get('X-Order-Token')
    if services.token_matches(order,token): return order
    raise PermissionDenied('You do not have access to this order.')

@api_view(['GET'])
@throttle_classes([])
def health(request):
    import redis
    try:
        with connection.cursor() as cursor: cursor.execute('SELECT 1')
        redis.Redis.from_url(settings.CELERY_BROKER_URL,socket_connect_timeout=1,socket_timeout=1).ping()
    except Exception:
        return Response({'status':'unavailable','service':'productstat-api'},status=503)
    return Response({'status':'ok','service':'productstat-api'})

@api_view(['GET'])
def bootstrap(request):
    if not request.session.session_key:
        request.session.create()
    company,_=CompanySettings.objects.get_or_create(pk=1)
    enabled=bool(settings.SSLCOMMERZ_STORE_ID and settings.SSLCOMMERZ_STORE_PASSWORD and (not settings.SSLCOMMERZ_SANDBOX or settings.PRODUCTSTAT_DEMO))
    return Response({'user':user_data(request.user),'company':SettingsSerializer(company).data,'csrfToken':get_token(request),'delivery_zones':list(DeliveryZone.objects.filter(is_active=True).values('id','name','charge')),'payment':{'cod':company.cod_enabled,'sslcommerz_enabled':enabled,'sandbox':settings.SSLCOMMERZ_SANDBOX},'demo':settings.PRODUCTSTAT_DEMO})

@api_view(['POST'])
@throttle_classes([LoginThrottle])
def register(request):
    serializer=RegisterSerializer(data=request.data);serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        services.advisory_lock('register:'+serializer.validated_data['email'].lower())
        if User.objects.filter(Q(email__iexact=serializer.validated_data['email'])|Q(username__iexact=serializer.validated_data['username'])).exists():
            raise ValidationError('An account with this username or email already exists.')
        user=User.objects.create_user(**serializer.validated_data)
        services.audit(user,'registered','user',user.id)
    login(request,user)
    return Response({'user':user_data(user),'csrfToken':get_token(request)},status=201)

@api_view(['POST'])
@throttle_classes([LoginThrottle])
def login_view(request):
    user=authenticate(request,username=str(request.data.get('username','')),password=str(request.data.get('password','')))
    if not user: raise ValidationError('Invalid username or password.')
    login(request,user)
    return Response({'user':user_data(user),'csrfToken':get_token(request)})

@api_view(['POST'])
def logout_view(request):
    logout(request)
    return Response({'user':None,'csrfToken':get_token(request)})

@api_view(['GET'])
def catalog(request,slug=None):
    queryset=Product.objects.filter(is_active=True,skus__is_active=True).distinct().prefetch_related('skus')
    if slug: return Response(ProductSerializer(get_object_or_404(queryset,slug=slug)).data)
    if request.query_params.get('q'): queryset=queryset.filter(Q(name__icontains=request.query_params['q'])|Q(category__icontains=request.query_params['q'])|Q(skus__code__icontains=request.query_params['q'])).distinct()
    if request.query_params.get('category'): queryset=queryset.filter(category=request.query_params['category'])
    sort=request.query_params.get('sort','newest')
    if sort.startswith('price_'): queryset=queryset.annotate(lowest_price=Min('skus__price')).order_by('-lowest_price' if sort=='price_desc' else 'lowest_price','id')
    else: queryset=queryset.order_by('name' if sort=='name' else '-created_at','id')
    page=services.integer(request.query_params.get('page','1'),maximum=100000)
    size=min(services.integer(request.query_params.get('page_size','24'),maximum=200),200)
    count=queryset.count()
    return Response({'count':count,'page':page,'page_size':size,'results':ProductSerializer(queryset[(page-1)*size:page*size],many=True).data,'categories':list(Product.objects.filter(is_active=True).order_by('category').values_list('category',flat=True).distinct())})

@api_view(['GET'])
def catalog_detail(request,slug):
    return Response(ProductSerializer(get_object_or_404(Product.objects.filter(is_active=True).prefetch_related('skus'),slug=slug)).data)

def cart_data(request):
    cart=request.session.get('cart',{})
    skus={str(s.id):s for s in SKU.objects.filter(id__in=cart.keys()).select_related('product')}
    items=[];subtotal=Decimal('0')
    for key,quantity in cart.items():
        sku=skus.get(key)
        if not sku: continue
        total=sku.price*quantity;subtotal+=total
        items.append({'sku_id':key,'quantity':quantity,'sku':SKUSerializer(sku).data,'product':{'name':sku.product.name,'slug':sku.product.slug,'image_url':sku.product.image_url},'line_total':str(total)})
    return {'items':items,'subtotal':str(subtotal)}

@api_view(['GET','POST','DELETE'])
def cart(request):
    if request.method=='DELETE': request.session['cart']={}
    if request.method=='POST':
        sku=get_object_or_404(SKU,pk=request.data.get('sku_id'),is_active=True,product__is_active=True)
        quantity=services.integer(request.data.get('quantity'),minimum=0,maximum=100)
        if quantity>sku.available: raise ValidationError('Requested quantity exceeds available stock.')
        contents=request.session.get('cart',{}).copy()
        if quantity: contents[str(sku.id)]=quantity
        else: contents.pop(str(sku.id),None)
        if len(contents)>100: raise ValidationError('Cart may contain at most 100 different SKUs.')
        request.session['cart']=contents
    return Response(cart_data(request))

@api_view(['POST'])
@throttle_classes([CheckoutThrottle])
def checkout(request):
    serializer=CheckoutSerializer(data=request.data);serializer.is_valid(raise_exception=True)
    if not request.session.session_key:
        request.session.create()
    # Cart/bootstrapping has already persisted this key. Two first checkout
    # requests must use the same identity, rather than racing to save random values.
    identity=request.session.get('checkout_identity') or request.session.session_key
    order,created=services.checkout(request.session.get('cart',{}),serializer.validated_data,request.headers.get('Idempotency-Key'),identity,request.user)
    payment_url=payments.initiate(order) if order.payment_method=='sslcommerz' and order.status=='pending_payment' else None
    request.session['cart']={}
    return Response({'order':order_data(order),'access_token':services.token_for(order),'payment_url':payment_url},status=201 if created else 200)

@api_view(['GET'])
def orders(request,pk=None):
    if pk: return Response(order_data(accessible_order(request,pk)))
    if not request.user.is_authenticated: return Response({'results':[]})
    queryset=order_queryset().filter(user=request.user).order_by('-created_at')
    page,size,items=page_items(request,queryset)
    return Response({'count':queryset.count(),'page':page,'page_size':size,'results':[order_data(order) for order in items]})

@api_view(['GET'])
def order_detail(request,pk):
    return Response(order_data(accessible_order(request,pk)))

@api_view(['POST'])
def cancel_order(request,pk):
    order=accessible_order(request,pk)
    serializer=CancelInput(data=request.data);serializer.is_valid(raise_exception=True)
    data=serializer.validated_data
    if 'lines' in data:
        data['lines']=[{**item,'order_line_id':str(item['order_line_id'])} for item in data['lines']]
    return Response(order_data(services.cancel_order(order.id,request.user,data.get('lines'))))

@api_view(['POST'])
def request_return(request,pk):
    order=accessible_order(request,pk)
    serializer=ReturnInput(data=request.data);serializer.is_valid(raise_exception=True)
    return Response(return_data(services.request_return(order.id,serializer.validated_data,request.user)),status=201)

@api_view(['GET'])
@permission_classes([IsOperator])
def staff_orders(request,pk=None):
    if pk: return Response(order_data(accessible_order(request,pk,staff=True)))
    queryset=order_queryset().filter(is_current=True).order_by('-created_at')
    if request.query_params.get('status'): queryset=queryset.filter(status=request.query_params['status'])
    if request.query_params.get('q'): queryset=queryset.filter(Q(number__icontains=request.query_params['q'])|Q(customer_name__icontains=request.query_params['q'])|Q(phone__icontains=request.query_params['q']))
    if request.query_params.get('source')=='live': queryset=queryset.filter(is_historical=False)
    page,size,items=page_items(request,queryset)
    return Response({'count':queryset.count(),'page':page,'page_size':size,'results':[order_data(order) for order in items]})

@api_view(['GET'])
@permission_classes([IsOperator])
def staff_order_detail(request,pk):
    return Response(order_data(accessible_order(request,pk,staff=True)))

@api_view(['POST'])
@permission_classes([IsOperator])
def staff_order_action(request,pk):
    get_object_or_404(Order,pk=pk)
    serializer=OrderAction(data=request.data);serializer.is_valid(raise_exception=True)
    data=serializer.validated_data
    if 'lines' in data: data['lines']=[{**item,'order_line_id':str(item['order_line_id'])} for item in data['lines']]
    return Response(order_data(services.order_action(pk,data['action'],data,request.user)))

@api_view(['GET'])
@permission_classes([IsOperator])
def staff_returns(request):
    queryset=ReturnRequest.objects.select_related('order').prefetch_related(Prefetch('lines',queryset=ReturnLine.objects.select_related('order_line'))).order_by('-created_at')
    if request.query_params.get('status'): queryset=queryset.filter(status=request.query_params['status'])
    page,size,items=page_items(request,queryset)
    return Response({'count':queryset.count(),'page':page,'page_size':size,'results':[return_data(item) for item in items]})

@api_view(['POST'])
@permission_classes([IsOperator])
def staff_return_action(request,pk):
    get_object_or_404(ReturnRequest,pk=pk)
    serializer=ReturnAction(data=request.data);serializer.is_valid(raise_exception=True)
    return Response(return_data(services.return_action(pk,serializer.validated_data['action'],serializer.validated_data,request.user)))

@api_view(['GET'])
@permission_classes([IsOperator])
def staff_refunds(request):
    queryset=Refund.objects.select_related('order').order_by('-created_at')
    page,size,items=page_items(request,queryset)
    return Response({'count':queryset.count(),'page':page,'page_size':size,'results':[refund_data(item) for item in items]})

@api_view(['POST'])
@permission_classes([IsAdministrator])
def confirm_refund(request,pk):
    get_object_or_404(Refund,pk=pk)
    serializer=RefundInput(data=request.data);serializer.is_valid(raise_exception=True)
    return Response(refund_data(services.confirm_refund(pk,serializer.validated_data['reference'],request.user)))

def _staff_products(request,pk=None):
    if request.method=='GET':
        queryset=Product.objects.all().prefetch_related('skus').order_by('name')
        if pk: return Response(ProductSerializer(get_object_or_404(queryset,pk=pk)).data)
        if request.query_params.get('q'):
            queryset=queryset.filter(Q(name__icontains=request.query_params['q'])|Q(skus__code__icontains=request.query_params['q'])|Q(category__icontains=request.query_params['q'])).distinct()
        if request.query_params.get('category'): queryset=queryset.filter(category=request.query_params['category'])
        page,size,items=page_items(request,queryset)
        return Response({'count':queryset.count(),'page':page,'page_size':size,'results':ProductSerializer(items,many=True).data})
    if not IsOperator().has_permission(request,None): raise PermissionDenied()
    if request.method=='PATCH' and not pk: raise ValidationError('Product ID required.')
    instance=get_object_or_404(Product,pk=pk) if pk else None
    serializer=ProductWriteSerializer(instance,data=request.data,partial=request.method=='PATCH');serializer.is_valid(raise_exception=True)
    values=dict(serializer.validated_data);skus=values.pop('skus',None)
    with transaction.atomic():
        if instance:
            product=Product.objects.select_for_update().get(pk=instance.pk)
            for key,value in values.items(): setattr(product,key,value)
            product.save()
        else: product=Product.objects.create(**values)
        if skus is not None:
            for item in skus:
                allowed={'code','label','attributes','price','is_active'}
                data={key:value for key,value in item.items() if key in allowed}
                if 'price' in data: data['price']=services.money(data['price'])
                if 'code' in data and (not isinstance(data['code'],str) or not 1<=len(data['code'])<=80): raise ValidationError('SKU code is required and must fit 80 characters.')
                if item.get('id'):
                    sku=get_object_or_404(SKU.objects.select_for_update(),pk=item['id'],product=product)
                    for key,value in data.items(): setattr(sku,key,value)
                    sku.full_clean();sku.save()
                else:
                    if not {'code','price'}<=set(data): raise ValidationError('New SKUs require code and price.')
                    sku=SKU(product=product,**data);sku.full_clean();sku.save()
        services.audit(request.user,'product_saved','product',product.id)
    return Response(ProductSerializer(product).data,status=201 if not instance else 200)

@api_view(['GET','POST'])
@permission_classes([IsStaffReader])
def staff_products(request):
    return _staff_products(request)

@api_view(['GET','PATCH'])
@permission_classes([IsStaffReader])
def staff_product_detail(request,pk):
    return _staff_products(request,pk)

@api_view(['GET','POST'])
@permission_classes([IsStaffReader])
def staff_inventory(request):
    if request.method=='POST':
        if not IsOperator().has_permission(request,None): raise PermissionDenied()
        serializer=InventoryInput(data=request.data);serializer.is_valid(raise_exception=True)
        data=serializer.validated_data
        get_object_or_404(SKU,pk=data['sku_id'])
        services.adjust_stock(data['sku_id'],data['delta'],data['reason'],request.user)
    queryset=SKU.objects.select_related('product').all().order_by('code')
    if request.query_params.get('q'): queryset=queryset.filter(Q(code__icontains=request.query_params['q'])|Q(product__name__icontains=request.query_params['q']))
    page,size,items=page_items(request,queryset,default=50)
    return Response({'count':queryset.count(),'page':page,'page_size':size,'results':[{'id':str(sku.id),'code':sku.code,'label':sku.label,'product_name':sku.product.name,'on_hand':sku.on_hand,'reserved':sku.reserved,'available':sku.available,'price':str(sku.price)} for sku in items]})

def _staff_users(request,pk=None):
    if request.method=='GET': return Response({'results':UserSerializer(User.objects.order_by('id')[:200],many=True).data})
    user=get_object_or_404(User,pk=pk) if pk else None
    if request.method=='PATCH' and not pk: raise ValidationError('User ID required.')
    if user and user.pk==request.user.pk and (request.data.get('role',user.role)!='administrator' or request.data.get('is_active') is False): raise ValidationError('You cannot remove your own administrator access.')
    serializer=UserSerializer(user,data=request.data,partial=bool(user));serializer.is_valid(raise_exception=True)
    if serializer.validated_data.get('role') not in {None,'customer','administrator','operator','analyst'}: raise ValidationError('Invalid role.')
    password=request.data.get('password')
    if not user and not password: raise ValidationError('A password is required for a new user.')
    if password:
        try: password_validation.validate_password(password,user)
        except DjangoValidationError as exc: raise ValidationError({'password':exc.messages})
    with transaction.atomic():
        user=serializer.save()
        if password: user.set_password(password);user.save(update_fields=['password'])
        services.audit(request.user,'user_saved','user',user.id,{'role':user.role,'is_active':user.is_active})
    return Response(UserSerializer(user).data)

@api_view(['GET','POST'])
@permission_classes([IsAdministrator])
def staff_users(request):
    return _staff_users(request)

@api_view(['PATCH'])
@permission_classes([IsAdministrator])
def staff_user_detail(request,pk):
    return _staff_users(request,pk)

@api_view(['GET','PATCH'])
@permission_classes([IsAdministrator])
@transaction.atomic
def staff_settings(request):
    company,_=CompanySettings.objects.get_or_create(pk=1)
    if request.method=='PATCH':
        serializer=SettingsSerializer(company,data=request.data,partial=True);serializer.is_valid(raise_exception=True);serializer.save()
        zones=request.data.get('delivery_zones')
        if zones is not None:
            if not isinstance(zones,list): raise ValidationError('delivery_zones must be a list.')
            for zone in zones:
                charge=services.money(zone.get('charge'))
                if zone.get('id'):
                    instance=get_object_or_404(DeliveryZone,pk=zone['id']);instance.name=str(zone.get('name',instance.name))[:100];instance.charge=charge;instance.is_active=bool(zone.get('is_active',True));instance.save()
                else: DeliveryZone.objects.create(name=str(zone.get('name',''))[:100],charge=charge)
        services.audit(request.user,'settings_saved','company',company.id)
    return Response({**SettingsSerializer(company).data,'delivery_zones':list(DeliveryZone.objects.values('id','name','charge','is_active'))})

@api_view(['GET'])
@permission_classes([IsAdministrator])
def audit_events(request):
    return Response({'results':[{'id':str(event.id),'event':event.event,'entity':event.entity,'reference':event.reference,'details':event.details,'actor':event.actor.username if event.actor else None,'created_at':dt(event.created_at)} for event in AuditEvent.objects.select_related('actor').order_by('-created_at')[:200]]})

@api_view(['POST'])
@authentication_classes([])
def payment_ipn(request):
    order=payments.validate_callback(request.data)
    return Response({'status':'verified','order_id':str(order.id)})

@api_view(['GET','POST'])
@authentication_classes([])
def payment_return(request):
    data=request.data if request.method=='POST' else request.query_params
    if data.get('val_id'):
        order=payments.validate_callback(data)
        return HttpResponseRedirect(settings.PUBLIC_BASE_URL+'/orders/'+str(order.id)+'?token='+services.token_for(order))
    return HttpResponseRedirect(settings.PUBLIC_BASE_URL+'/checkout?payment=incomplete')
