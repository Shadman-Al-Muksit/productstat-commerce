"""Preserve observed settlement history without inventing missing partial dates.

Complete, uniquely referenced live settlement audits recover increments. Otherwise
only the unrepresented legacy aggregate is observed at its saved timestamp; its
source explicitly records that finer history is unavailable. Unknown legacy dates
remain NULL and are excluded from dated activity, rather than assigned a date.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from django.db import migrations
from django.db.models import Count


def backfill_settlements(apps,schema_editor):
    Payment=apps.get_model('commerce','Payment')
    Settlement=apps.get_model('commerce','PaymentSettlement')
    Audit=apps.get_model('commerce','AuditEvent')
    alias=schema_editor.connection.alias
    audits=defaultdict(list)
    for audit in Audit.objects.using(alias).filter(event='settle_cod',entity='order').order_by('created_at','id').values('reference','details','created_at','actor_id'):
        audits[audit['reference']].append(audit)
    cod_counts=dict(Payment.objects.using(alias).filter(method='cod').values('order_id').annotate(count=Count('id')).values_list('order_id','count'))
    existing=defaultdict(dict)
    for event in Settlement.objects.using(alias).values('payment_id','reference','amount'):
        existing[event['payment_id']][event['reference']]=event['amount']
    pending=[]
    for payment in Payment.objects.using(alias).filter(settled_amount__gt=0).values('id','order_id','method','settled_amount','settled_at','order__is_historical').iterator(chunk_size=1000):
        represented=existing[payment['id']]
        represented_total=sum(represented.values(),Decimal('0'))
        aggregate=payment['settled_amount']
        if represented_total>aggregate:
            raise RuntimeError('Settlement event totals exceed a saved payment aggregate; reconciliation is required before migration.')
        if represented_total==aggregate:
            continue
        recovered=[]; references=set(); valid=True
        candidates=audits.get(str(payment['order_id']),[]) if payment['method']=='cod' and not payment['order__is_historical'] and cod_counts.get(payment['order_id'])==1 else []
        for audit in candidates:
            details=audit['details']
            try:
                amount=Decimal(str(details['amount']))
                reference=str(details['reference']).strip()
                if not amount.is_finite() or amount<=0 or amount!=amount.quantize(Decimal('.01')) or not reference or len(reference)>200 or reference in references:
                    raise ValueError
            except (KeyError,TypeError,InvalidOperation,ValueError):
                valid=False;break
            references.add(reference)
            recovered.append((reference,amount,audit['created_at'],audit['actor_id']))
        recovered_values={reference:amount for reference,amount,_,_ in recovered}
        complete=bool(recovered) and valid and sum(recovered_values.values(),Decimal('0'))==aggregate and all(recovered_values.get(reference)==amount for reference,amount in represented.items())
        if complete:
            for reference,amount,observed_at,actor_id in recovered:
                if reference not in represented:
                    pending.append(Settlement(payment_id=payment['id'],amount=amount,settled_at=observed_at,reference=reference,actor_id=actor_id,source='audit_backfill'))
        else:
            pending.append(Settlement(payment_id=payment['id'],amount=aggregate-represented_total,settled_at=payment['settled_at'],reference='legacy-aggregate:'+str(payment['id']),source='legacy_aggregate'))
        if len(pending)>=1000:
            Settlement.objects.using(alias).bulk_create(pending,batch_size=1000);pending=[]
    if pending:
        Settlement.objects.using(alias).bulk_create(pending,batch_size=1000)


class Migration(migrations.Migration):
    dependencies=[('commerce','0003_commerce_integrity_tax_and_recovery')]
    operations=[migrations.RunPython(backfill_settlements,migrations.RunPython.noop)]
