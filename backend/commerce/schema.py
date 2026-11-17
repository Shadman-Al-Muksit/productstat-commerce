"""Explicit wire schemas for DRF function views, used by OpenAPI and generated clients."""
from rest_framework import serializers as s
from drf_spectacular.utils import extend_schema,OpenApiParameter,OpenApiResponse
from drf_spectacular.types import OpenApiTypes
from .serializers import ProductSerializer,ProductWriteSerializer,UserSerializer,RegisterSerializer,CheckoutSerializer,SettingsSerializer

class Money(s.DecimalField):
    def __init__(self,**kwargs): super().__init__(max_digits=14,decimal_places=2,**kwargs)
class Address(s.Serializer):
    line1=s.CharField();city=s.CharField();area=s.CharField(required=False);postal_code=s.CharField(required=False)
class Zone(s.Serializer):
    id=s.IntegerField();name=s.CharField();charge=Money();is_active=s.BooleanField(required=False)
class Company(SettingsSerializer):
    delivery_zones=Zone(many=True,required=False)
    class Meta(SettingsSerializer.Meta):
        fields=SettingsSerializer.Meta.fields+['delivery_zones']
class PaymentConfiguration(s.Serializer):
    cod=s.BooleanField();sslcommerz_enabled=s.BooleanField();sandbox=s.BooleanField()
class Bootstrap(s.Serializer):
    user=UserSerializer(allow_null=True);company=Company();csrfToken=s.CharField();delivery_zones=Zone(many=True);payment=PaymentConfiguration();demo=s.BooleanField()
class LoginInput(s.Serializer):
    username=s.CharField(max_length=150);password=s.CharField(write_only=True,max_length=128)
class AuthResult(s.Serializer):
    user=UserSerializer(allow_null=True);csrfToken=s.CharField()
class ProductPage(s.Serializer):
    count=s.IntegerField();page=s.IntegerField();page_size=s.IntegerField();categories=s.ListField(child=s.CharField());results=ProductSerializer(many=True)
class ProductList(s.Serializer):
    count=s.IntegerField();page=s.IntegerField();page_size=s.IntegerField();results=ProductSerializer(many=True)
class CartSKU(s.Serializer):
    id=s.UUIDField();code=s.CharField();label=s.CharField();attributes=s.DictField();price=Money();available=s.IntegerField();is_active=s.BooleanField()
class CartProduct(s.Serializer):
    name=s.CharField();slug=s.CharField();image_url=s.CharField()
class CartLine(s.Serializer):
    sku_id=s.UUIDField();quantity=s.IntegerField();sku=CartSKU();product=CartProduct();line_total=Money()
class CartResult(s.Serializer):
    items=CartLine(many=True);subtotal=Money()
class CartInput(s.Serializer):
    sku_id=s.UUIDField();quantity=s.IntegerField(min_value=0,max_value=100)
class OrderLine(s.Serializer):
    id=s.UUIDField();sku_id=s.UUIDField(allow_null=True);sku_code=s.CharField();product_name=s.CharField();variant_name=s.CharField();quantity=s.IntegerField();cancelled_quantity=s.IntegerField();shipped_quantity=s.IntegerField();delivered_quantity=s.IntegerField();returned_quantity=s.IntegerField();unit_price=Money();discount_total=Money();tax_total=Money();line_total=Money()
class Shipment(s.Serializer):
    id=s.UUIDField();state=s.CharField();carrier=s.CharField();tracking_number=s.CharField();dispatched_at=s.DateTimeField(allow_null=True);delivered_at=s.DateTimeField(allow_null=True)
class Payment(s.Serializer):
    id=s.UUIDField();method=s.CharField();status=s.CharField();amount=Money();settled_amount=Money();is_sandbox=s.BooleanField();collected_at=s.DateTimeField(allow_null=True);settled_at=s.DateTimeField(allow_null=True)
class ReturnLine(s.Serializer):
    id=s.UUIDField();order_line_id=s.UUIDField();product_name=s.CharField();quantity=s.IntegerField();accepted_quantity=s.IntegerField();restock_quantity=s.IntegerField();disposition=s.CharField()
class Return(s.Serializer):
    id=s.UUIDField();order_id=s.UUIDField();order_number=s.CharField();status=s.CharField();reason=s.CharField();created_at=s.DateTimeField();received_at=s.DateTimeField(allow_null=True);inspected_at=s.DateTimeField(allow_null=True);lines=ReturnLine(many=True)
class Refund(s.Serializer):
    id=s.UUIDField();order_id=s.UUIDField();order_number=s.CharField();amount=Money();status=s.CharField();reason=s.CharField();reference=s.CharField();created_at=s.DateTimeField();confirmed_at=s.DateTimeField(allow_null=True)
class Order(s.Serializer):
    id=s.UUIDField();number=s.CharField();status=s.CharField();payment_method=s.CharField();customer_name=s.CharField();email=s.CharField();phone=s.CharField();address=Address();subtotal=Money();discount_total=Money();shipping_total=Money();tax_total=Money();grand_total=Money();collected_total=Money();refunded_total=Money();created_at=s.DateTimeField(allow_null=True);confirmed_at=s.DateTimeField(allow_null=True);dispatched_at=s.DateTimeField(allow_null=True);delivered_at=s.DateTimeField(allow_null=True);reservation_expires_at=s.DateTimeField(allow_null=True);is_historical=s.BooleanField();is_current=s.BooleanField();supersedes_id=s.UUIDField(allow_null=True);source=s.CharField();lines=OrderLine(many=True);shipments=Shipment(many=True);payments=Payment(many=True);returns=Return(many=True);refunds=Refund(many=True)
    prepared_at=s.DateTimeField(allow_null=True)
class CheckoutResult(s.Serializer):
    order=Order();access_token=s.CharField();payment_url=s.URLField(allow_null=True)
class Page(s.Serializer):
    count=s.IntegerField();page=s.IntegerField();page_size=s.IntegerField()
class OrderPage(Page): results=Order(many=True)
class ReturnPage(Page): results=Return(many=True)
class RefundPage(Page): results=Refund(many=True)
class QuantityInput(s.Serializer):
    order_line_id=s.UUIDField();quantity=s.IntegerField(min_value=1)
class CancelInput(s.Serializer): lines=QuantityInput(many=True,required=False)
class ReturnInput(s.Serializer):
    reason=s.CharField();lines=QuantityInput(many=True)
class OrderAction(CancelInput):
    action=s.ChoiceField(choices=['prepare','dispatch','deliver','fail','return_to_origin','collect_cod','settle_cod','cancel']);carrier=s.CharField(required=False,allow_blank=True,max_length=100);tracking_number=s.CharField(required=False,allow_blank=True,max_length=120);amount=Money(required=False);reference=s.CharField(required=False,max_length=200)
class InspectionLine(s.Serializer):
    id=s.UUIDField();accepted_quantity=s.IntegerField(min_value=0);restock_quantity=s.IntegerField(min_value=0);disposition=s.ChoiceField(choices=['restock','quarantine','dispose'])
class ReturnAction(s.Serializer):
    action=s.ChoiceField(choices=['approve','reject','receive','inspect']);lines=InspectionLine(many=True,required=False)
class RefundInput(s.Serializer): reference=s.CharField(max_length=150)
class InventorySKU(s.Serializer):
    id=s.UUIDField();code=s.CharField();label=s.CharField();product_name=s.CharField();on_hand=s.IntegerField();reserved=s.IntegerField();available=s.IntegerField();price=Money()
class InventoryResult(Page): results=InventorySKU(many=True)
class InventoryInput(s.Serializer):
    sku_id=s.UUIDField();delta=s.IntegerField(min_value=-1000000,max_value=1000000);reason=s.CharField(max_length=200)
class UserList(s.Serializer): results=UserSerializer(many=True)
class UserInput(UserSerializer):
    password=s.CharField(required=False,write_only=True)
    class Meta(UserSerializer.Meta): fields=UserSerializer.Meta.fields+['password']
class Audit(s.Serializer):
    id=s.UUIDField();event=s.CharField();entity=s.CharField();reference=s.CharField();details=s.DictField();actor=s.CharField(allow_null=True);created_at=s.DateTimeField()
class AuditList(s.Serializer): results=Audit(many=True)
class CallbackInput(s.Serializer):
    tran_id=s.CharField();val_id=s.CharField();status=s.CharField(required=False)
class CallbackResult(s.Serializer):
    status=s.CharField();order_id=s.UUIDField()
class Health(s.Serializer):
    status=s.CharField();service=s.CharField()

def annotate_core(views):
    specs={
        'health':{'get':(None,Health)},'bootstrap':{'get':(None,Bootstrap)},
        'register':{'post':(RegisterSerializer,AuthResult)},'login_view':{'post':(LoginInput,AuthResult)},'logout_view':{'post':(None,AuthResult)},
        'catalog':{'get':(None,ProductPage)},'catalog_detail':{'get':(None,ProductSerializer)},
        'cart':{'get':(None,CartResult),'post':(CartInput,CartResult),'delete':(None,CartResult)},
        'checkout':{'post':(CheckoutSerializer,CheckoutResult)},'orders':{'get':(None,OrderPage)},'order_detail':{'get':(None,Order)},'cancel_order':{'post':(CancelInput,Order)},'request_return':{'post':(ReturnInput,Return)},
        'staff_orders':{'get':(None,OrderPage)},'staff_order_detail':{'get':(None,Order)},'staff_order_action':{'post':(OrderAction,Order)},
        'staff_returns':{'get':(None,ReturnPage)},'staff_return_action':{'post':(ReturnAction,Return)},'staff_refunds':{'get':(None,RefundPage)},'confirm_refund':{'post':(RefundInput,Refund)},
        'staff_products':{'get':(None,ProductList),'post':(ProductWriteSerializer,ProductSerializer)},'staff_product_detail':{'get':(None,ProductSerializer),'patch':(ProductWriteSerializer,ProductSerializer)},
        'staff_inventory':{'get':(None,InventoryResult),'post':(InventoryInput,InventoryResult)},'staff_users':{'get':(None,UserList),'post':(UserInput,UserSerializer)},'staff_user_detail':{'patch':(UserInput,UserSerializer)},
        'staff_settings':{'get':(None,Company),'patch':(Company,Company)},'audit_events':{'get':(None,AuditList)},
        'payment_ipn':{'post':(CallbackInput,CallbackResult)},'payment_return':{'get':(None,None),'post':(CallbackInput,None)},
    }
    page_parameters=[OpenApiParameter('page',int,description='Page number, starting at one.'),OpenApiParameter('page_size',int,description='Rows per page; maximum 100 for operational lists.')]
    for name,methods in specs.items():
        view=getattr(views,name)
        for method,(request,response) in methods.items():
            parameters=[]
            if name in ['catalog','orders','staff_orders','staff_returns','staff_refunds','staff_products','staff_inventory'] and method=='get': parameters+=page_parameters
            if name in ['catalog','staff_orders','staff_inventory','staff_products'] and method=='get': parameters+=[OpenApiParameter('q',str)]
            if name=='catalog': parameters+=[OpenApiParameter('category',str),OpenApiParameter('sort',str,enum=['newest','name','price_asc','price_desc'])]
            if name in ['staff_orders','staff_returns']: parameters+=[OpenApiParameter('status',str)]
            if name in ['order_detail','cancel_order','request_return']: parameters+=[OpenApiParameter('token',str,description='Guest order access token; prefer X-Order-Token header when available.')]
            if name=='checkout': parameters+=[OpenApiParameter('Idempotency-Key',str,location=OpenApiParameter.HEADER,required=True)]
            code=201 if (name in ['register','checkout','request_return'] or name=='staff_products' and method=='post') else 200
            responses={code:response} if response is not None else {302:OpenApiResponse(description='Redirect to the storefront order page after independently verified provider validation.')}
            if name=='checkout': responses[200]=response
            view=extend_schema(methods=[method],operation_id=f'{name}_{method}',request=request,responses=responses,parameters=parameters,tags=['Payments' if name.startswith('payment') else 'Staff' if name.startswith('staff') or name in ['confirm_refund','audit_events'] else 'Commerce'])(view)
        setattr(views,name,view)
