"""Read-only operational attention signals; no customer data or external delivery."""
from datetime import timedelta
from decimal import Decimal
from django.db.models import DecimalField,F,OuterRef,Q,Subquery,Sum,Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from .models import ImportBatch,Order,OutboxEvent,Payment,Refund

OUTBOX_ATTEMPT_LIMIT=8  # Matches the durable dispatcher's terminal retry limit.
SAMPLE_LIMIT=20

def operations_health(now=None):
    now=now or timezone.now()
    cutoff=now-timedelta(hours=48)
    overdue=Order.objects.filter(is_historical=False,is_current=True,payment_method='cod',status__in=['confirmed','preparing']).annotate(accepted_at=Coalesce('confirmed_at','created_at')).filter(accepted_at__lte=cutoff).order_by('accepted_at','id')
    exhausted=OutboxEvent.objects.filter(attempts__gte=OUTBOX_ATTEMPT_LIMIT).filter(Q(status__in=['pending','failed'])|Q(status='processing',next_attempt_at__lte=now)|Q(status='processing',next_attempt_at__isnull=True)).order_by('-created_at','id')
    failed_imports=ImportBatch.objects.filter(status='failed').order_by('-created_at','id')
    money_field=DecimalField(max_digits=14,decimal_places=2)
    captured=Payment.objects.filter(order_id=OuterRef('pk'),status='exception').values('order_id').annotate(total=Sum('amount')).values('total')
    refunded=Refund.objects.filter(order_id=OuterRef('pk'),status='confirmed').values('order_id').annotate(total=Sum('amount')).values('total')
    exceptions=Order.objects.filter(is_historical=False,is_current=True,payments__status='exception').annotate(exception_amount=Coalesce(Subquery(captured,output_field=money_field),Value(Decimal('0')),output_field=money_field),refunded_amount=Coalesce(Subquery(refunded,output_field=money_field),Value(Decimal('0')),output_field=money_field)).filter(exception_amount__gt=F('refunded_amount')).distinct().order_by('-created_at','id')
    counts={'overdue_cod_orders':overdue.count(),'failed_outbox_jobs':exhausted.count(),'failed_imports':failed_imports.count(),'payment_exceptions':exceptions.count()}
    return {
        'status':'attention' if any(counts.values()) else 'ok',
        'checked_at':now.isoformat(),
        'counts':counts,
        'overdue_cod_orders':[{'id':str(order.id),'number':order.number,'status':order.status,'created_at':order.created_at.isoformat(),'confirmed_at':order.confirmed_at.isoformat() if order.confirmed_at else None,'age_hours':round((now-order.accepted_at).total_seconds()/3600,2)} for order in overdue[:SAMPLE_LIMIT]],
        'failed_outbox_jobs':[{'id':str(event.id),'kind':event.kind,'attempts':event.attempts} for event in exhausted[:SAMPLE_LIMIT]],
        'failed_imports':[{'id':str(batch.id),'kind':batch.kind,'status':batch.status,'created_at':batch.created_at.isoformat()} for batch in failed_imports[:SAMPLE_LIMIT]],
        'payment_exceptions':[{'id':str(order.id),'number':order.number,'unreconciled_amount':str(order.exception_amount-order.refunded_amount)} for order in exceptions[:SAMPLE_LIMIT]],
        'sample_limit':SAMPLE_LIMIT,
    }
