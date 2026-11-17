from decimal import Decimal
from urllib.parse import urlparse
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import Product,SKU,User,DeliveryZone,CompanySettings

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model=User
        fields=['id','username','email','first_name','last_name','role','is_active']

class SKUSerializer(serializers.ModelSerializer):
    available=serializers.IntegerField(read_only=True)
    class Meta:
        model=SKU
        fields=['id','code','label','attributes','price','available','is_active']

class ProductSerializer(serializers.ModelSerializer):
    skus=SKUSerializer(many=True,read_only=True)
    min_price=serializers.SerializerMethodField()
    total_available=serializers.SerializerMethodField()
    class Meta:
        model=Product
        fields=['id','name','slug','description','category','image_url','is_active','created_at','skus','min_price','total_available']
    @extend_schema_field(serializers.DecimalField(max_digits=12,decimal_places=2,allow_null=True))
    def get_min_price(self,obj):
        values=[sku.price for sku in obj.skus.all() if sku.is_active]
        return str(min(values)) if values else None
    def get_total_available(self,obj) -> int:
        return sum(sku.available for sku in obj.skus.all() if sku.is_active)

class SKUWriteSerializer(serializers.Serializer):
    id=serializers.UUIDField(required=False)
    code=serializers.CharField(max_length=80,required=False)
    label=serializers.CharField(max_length=120,required=False,allow_blank=True)
    attributes=serializers.DictField(required=False)
    price=serializers.DecimalField(max_digits=12,decimal_places=2,min_value=Decimal('0'),required=False)
    is_active=serializers.BooleanField(required=False)
    def validate(self,value):
        if 'id' not in value and not {'code','price'} <= set(value):
            raise serializers.ValidationError('New SKUs require code and price.')
        return value

class ProductWriteSerializer(serializers.ModelSerializer):
    skus=SKUWriteSerializer(many=True,required=False,write_only=True)
    class Meta:
        model=Product
        fields=['name','slug','description','category','image_url','is_active','skus']
    def validate_image_url(self,value):
        if value and not (value.startswith('/products/') or urlparse(value).scheme=='https'):
            raise serializers.ValidationError('Use a local /products/ asset or an HTTPS image URL.')
        return value

class RegisterSerializer(serializers.Serializer):
    username=serializers.CharField(max_length=150)
    email=serializers.EmailField()
    password=serializers.CharField(write_only=True,max_length=128)
    def validate(self,data):
        if User.objects.filter(username__iexact=data['username']).exists() or User.objects.filter(email__iexact=data['email']).exists():
            raise serializers.ValidationError('An account with this username or email already exists.')
        try: password_validation.validate_password(data['password'],User(username=data['username'],email=data['email']))
        except DjangoValidationError as exc: raise serializers.ValidationError({'password':exc.messages})
        return data

class CheckoutSerializer(serializers.Serializer):
    customer_name=serializers.CharField(max_length=150)
    email=serializers.EmailField(required=False,allow_blank=True,default='')
    phone=serializers.RegexField(r'^\+?8801[3-9]\d{8}$|^01[3-9]\d{8}$',max_length=25)
    address=serializers.DictField()
    delivery_zone_id=serializers.IntegerField(min_value=1)
    payment_method=serializers.ChoiceField(choices=['cod','sslcommerz'])
    def validate_address(self,value):
        allowed=['line1','area','city','postal_code']
        if not all(isinstance(value.get(key),str) and value[key].strip() for key in ['line1','city']):
            raise serializers.ValidationError('Address line1 and city are required.')
        if any(len(str(item))>500 for item in value.values()): raise serializers.ValidationError('Address field too long.')
        return {key:str(value.get(key,'')) for key in allowed}

class SettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model=CompanySettings
        fields=['name','support_email','currency','timezone','return_window_days','cod_enabled','logo_url','tax_rate']
        read_only_fields=['currency','timezone']
    def validate_return_window_days(self,value):
        if not 1<=value<=30: raise serializers.ValidationError('Return window must be between 1 and 30 days.')
        return value
