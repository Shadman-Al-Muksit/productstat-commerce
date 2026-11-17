import uuid
from decimal import Decimal
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError as ModelValidationError

ZERO = Decimal('0.00')

class User(AbstractUser):
    role = models.CharField(max_length=20, choices=[(r,r) for r in ['customer','administrator','operator','analyst']], default='customer')
    class Meta:
        constraints = [models.UniqueConstraint(Lower('username'),name='user_username_case_unique'),models.UniqueConstraint(Lower('email'),condition=~Q(email=''),name='user_email_case_unique')]

class CompanySettings(models.Model):
    name = models.CharField(max_length=150, default='ProductStat Commerce')
    support_email = models.EmailField(default='support@productstat.local')
    currency = models.CharField(max_length=3, default='BDT')
    timezone = models.CharField(max_length=40, default='Asia/Dhaka')
    return_window_days = models.PositiveIntegerField(default=7)
    cod_enabled = models.BooleanField(default=True)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO, validators=[MinValueValidator(ZERO),MaxValueValidator(Decimal('100'))])
    logo_url = models.URLField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(tax_rate__gte=0,tax_rate__lte=100),name='company_tax_rate_range')]

class DeliveryZone(models.Model):
    name = models.CharField(max_length=100, unique=True)
    charge = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    is_active = models.BooleanField(default=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(charge__gte=0),name='delivery_nonnegative_charge')]

class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100, db_index=True)
    image_url = models.CharField(max_length=1000,blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

class SKU(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='skus')
    code = models.CharField(max_length=80, unique=True)
    label = models.CharField(max_length=120, blank=True)
    attributes = models.JSONField(default=dict)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    on_hand = models.PositiveIntegerField(default=0)
    reserved = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(on_hand__gte=F('reserved')),name='stock_covers_reservations'),models.CheckConstraint(condition=Q(price__gte=0),name='sku_nonnegative_price'),models.CheckConstraint(condition=Q(cost__isnull=True)|Q(cost__gte=0),name='sku_nonnegative_cost')]
    @property
    def available(self):
        return self.on_hand - self.reserved

class Order(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.CharField(max_length=40, unique=True)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='orders')
    customer_name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=25)
    address = models.JSONField(default=dict)
    status = models.CharField(max_length=30, default='confirmed', db_index=True)
    payment_method = models.CharField(max_length=20, default='cod')
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    discount_total = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    shipping_total = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    tax_total = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    grand_total = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    created_at = models.DateTimeField(default=__import__('django.utils.timezone',fromlist=['now']).now, db_index=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    prepared_at = models.DateTimeField(null=True, blank=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    reservation_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    source = models.CharField(max_length=100, default='live')
    external_id = models.CharField(max_length=150, null=True, blank=True)
    is_historical = models.BooleanField(default=False)
    guest_token_hash = models.CharField(max_length=64, blank=True)
    idempotency_key = models.CharField(max_length=100, null=True, blank=True, unique=True)
    checkout_fingerprint = models.CharField(max_length=64, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['source','external_id'],name='unique_external_order'),models.CheckConstraint(condition=Q(subtotal__gte=0,discount_total__gte=0,shipping_total__gte=0,tax_total__gte=0,grand_total__gte=0)&Q(discount_total__lte=F('subtotal')),name='order_nonnegative_amounts')]

class OrderLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='lines')
    sku = models.ForeignKey(SKU, null=True, blank=True, on_delete=models.PROTECT, related_name='order_lines')
    sku_code = models.CharField(max_length=80)
    product_name = models.CharField(max_length=200)
    variant_name = models.CharField(max_length=120, blank=True)
    quantity = models.PositiveIntegerField()
    cancelled_quantity = models.PositiveIntegerField(default=0)
    shipped_quantity = models.PositiveIntegerField(default=0)
    delivered_quantity = models.PositiveIntegerField(default=0)
    returned_quantity = models.PositiveIntegerField(default=0)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_total = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    tax_total = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    source_line_id = models.CharField(max_length=150, null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['order','source_line_id'],name='unique_external_line'),models.CheckConstraint(condition=Q(quantity__gt=0),name='positive_order_quantity'),models.CheckConstraint(condition=Q(cancelled_quantity__lte=F('quantity')),name='cancel_not_above_order'),models.CheckConstraint(condition=Q(delivered_quantity__lte=F('shipped_quantity')),name='delivery_not_above_shipped'),models.CheckConstraint(condition=Q(returned_quantity__lte=F('delivered_quantity')),name='return_not_above_delivered'),models.CheckConstraint(condition=Q(quantity__gte=F('cancelled_quantity')+F('shipped_quantity')),name='shipped_cancel_within_order'),models.CheckConstraint(condition=Q(unit_price__gte=0,discount_total__gte=0,tax_total__gte=0)&Q(discount_total__lte=F('unit_price')*F('quantity')),name='line_valid_amounts')]
    @property
    def net_unit_price(self):
        return self.unit_price - self.discount_total / self.quantity

class Shipment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='shipments')
    state = models.CharField(max_length=30, default='dispatched')
    tracking_number = models.CharField(max_length=120, blank=True)
    carrier = models.CharField(max_length=100, blank=True)
    dispatched_at = models.DateTimeField()
    delivered_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

class ShipmentLine(models.Model):
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name='lines')
    order_line = models.ForeignKey(OrderLine, on_delete=models.PROTECT, related_name='shipment_lines')
    quantity = models.PositiveIntegerField()
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0),name='shipment_positive_quantity'),models.UniqueConstraint(fields=['shipment','order_line'],name='shipment_unique_line')]

class Payment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='payments')
    method = models.CharField(max_length=20)
    status = models.CharField(max_length=20, default='pending')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    settled_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    provider_transaction_id = models.CharField(max_length=150, null=True, blank=True, unique=True)
    provider_validation_id = models.CharField(max_length=150, blank=True)
    gateway_url = models.URLField(max_length=1000, blank=True)
    is_sandbox = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    collected_at = models.DateTimeField(null=True, blank=True)
    settled_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(amount__gte=0,settled_amount__gte=0)&Q(settled_amount__lte=F('amount')),name='payment_valid_amounts')]

class SettlementQuerySet(models.QuerySet):
    def update(self,**kwargs):
        raise ModelValidationError('Settlement events are immutable. Record a separate correcting event through a reviewed reconciliation process.')
    def delete(self):
        raise ModelValidationError('Settlement events cannot be deleted.')

class PaymentSettlement(models.Model):
    """An observed cash settlement increment, never a cumulative activity measure."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name='settlements')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    settled_at = models.DateTimeField(null=True,blank=True,db_index=True)
    reference = models.CharField(max_length=200)
    actor = models.ForeignKey(User,null=True,blank=True,on_delete=models.SET_NULL)
    source = models.CharField(max_length=30,default='live',choices=[(value,value) for value in ['live','audit_backfill','legacy_aggregate','import','demo']])
    created_at = models.DateTimeField(auto_now_add=True)
    objects = SettlementQuerySet.as_manager()
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0),name='settlement_positive_amount'),models.UniqueConstraint(fields=['payment','reference'],name='settlement_payment_reference_unique'),models.CheckConstraint(condition=Q(settled_at__isnull=False)|Q(source='legacy_aggregate'),name='settlement_observed_date_required')]
    def save(self,*args,**kwargs):
        if not self._state.adding:
            raise ModelValidationError('Settlement events are immutable.')
        return super().save(*args,**kwargs)
    def delete(self,*args,**kwargs):
        raise ModelValidationError('Settlement events cannot be deleted.')

class ReturnRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='returns')
    status = models.CharField(max_length=20, default='requested')
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    received_at = models.DateTimeField(null=True, blank=True)
    inspected_at = models.DateTimeField(null=True, blank=True)

class ReturnLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    return_request = models.ForeignKey(ReturnRequest, on_delete=models.CASCADE, related_name='lines')
    order_line = models.ForeignKey(OrderLine, on_delete=models.PROTECT, related_name='return_lines')
    quantity = models.PositiveIntegerField()
    accepted_quantity = models.PositiveIntegerField(default=0)
    restock_quantity = models.PositiveIntegerField(default=0)
    disposition = models.CharField(max_length=20, default='quarantine')
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0)&Q(accepted_quantity__lte=F('quantity'))&Q(restock_quantity__lte=F('accepted_quantity')),name='return_valid_quantities'),models.UniqueConstraint(fields=['return_request','order_line'],name='return_unique_line')]

class Refund(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='refunds')
    return_request = models.ForeignKey(ReturnRequest, null=True, blank=True, on_delete=models.PROTECT, related_name='refunds')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=20, default='pending')
    reason = models.CharField(max_length=200)
    reference = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0),name='refund_positive_amount')]

class StockMovement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sku = models.ForeignKey(SKU, on_delete=models.PROTECT, related_name='movements')
    on_hand_delta = models.IntegerField(default=0)
    reserved_delta = models.IntegerField(default=0)
    kind = models.CharField(max_length=40)
    reference = models.CharField(max_length=200)
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

class RefundLine(models.Model):
    refund = models.ForeignKey(Refund, on_delete=models.CASCADE, related_name='lines')
    order_line = models.ForeignKey(OrderLine, on_delete=models.PROTECT, related_name='refund_lines')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    shipping_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0,tax_amount__gte=0,shipping_amount__gte=0)&Q(amount__gte=F('tax_amount')+F('shipping_amount')),name='refund_line_valid_amounts'),models.UniqueConstraint(fields=['refund','order_line'],name='refund_unique_line')]

class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    event = models.CharField(max_length=80)
    entity = models.CharField(max_length=80)
    reference = models.CharField(max_length=150)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

class ImportBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=30)
    status = models.CharField(max_length=30, default='queued')
    file = models.FileField(upload_to='imports/%Y/%m/')
    filename = models.CharField(max_length=250)
    source_name = models.CharField(max_length=100)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    progress = models.PositiveIntegerField(default=0)
    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    error_rows = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list)
    preview = models.JSONField(default=list)
    result = models.JSONField(default=dict)
    committed_at = models.DateTimeField(null=True, blank=True)

class OutboxEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=80)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, default='pending')
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
