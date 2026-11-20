from decimal import Decimal
import re
from urllib.parse import unquote, urlsplit
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import Product,SKU,User,DeliveryZone,CompanySettings


def validate_image_reference(value):
    """Accept public image references without fetching or rewriting their content."""
    message = 'Use a local /products/ image path or a valid HTTPS image URL without credentials.'
    if not isinstance(value, str) or len(value) > 1000:
        raise serializers.ValidationError(message)
    if value == '':
        return value
    if re.search(r'%(?![0-9a-fA-F]{2})', value):
        raise serializers.ValidationError(message)
    # Decode repeatedly so encoded/double-encoded traversal and backslashes
    # cannot turn an approved local asset into another application path.
    decoded = value
    while True:
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    if (any(ord(char) < 33 or 127 <= ord(char) <= 159 for char in value)
            or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in decoded)
            or '\\' in decoded):
        raise serializers.ValidationError(message)
    try:
        parsed = urlsplit(value)
        decoded_path = parsed.path
        while True:
            next_path = unquote(decoded_path)
            if next_path == decoded_path:
                break
            decoded_path = next_path
        if any(segment in {'.', '..'} for segment in decoded_path.split('/')):
            raise serializers.ValidationError(message)
        if value.startswith('/products/'):
            if parsed.scheme or parsed.netloc or not decoded_path.startswith('/products/'):
                raise serializers.ValidationError(message)
            asset_segments = decoded_path[len('/products/'):].split('/')
            if not all(asset_segments):
                raise serializers.ValidationError(message)
        else:
            URLValidator(schemes=['https'])(value)
            if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
                    or parsed.password is not None or (parsed.port is not None and not 1 <= parsed.port <= 65535)):
                raise serializers.ValidationError(message)
    except (DjangoValidationError, ValueError):
        raise serializers.ValidationError(message) from None
    return value


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
    def validate_attributes(self,value):
        # Preserve arbitrary product metadata; validate only the image/colour
        # keys interpreted by the storefront and staff editor.
        if 'image_url' in value:
            value['image_url'] = validate_image_reference(value['image_url'])
        if 'color' in value:
            color = value['color']
            if (not isinstance(color, str) or len(color) > 120
                    or any(ord(char) < 32 or ord(char) == 127 for char in color)):
                raise serializers.ValidationError({'color': 'Use a colour name of at most 120 characters.'})
        if 'color_hex' in value:
            color_hex = value['color_hex']
            if not isinstance(color_hex, str) or (color_hex and not re.fullmatch(r'#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?', color_hex)):
                raise serializers.ValidationError({'color_hex': 'Use #RGB or #RRGGBB, or leave blank.'})
        return value
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
        return validate_image_reference(value)

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
