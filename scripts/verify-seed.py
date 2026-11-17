"""Prove a repeated seed does not change existing sales or stock."""
import json
import os
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.core.management import call_command
from django.db.models import Sum
from commerce.models import Order, OrderLine, SKU, StockMovement
def snapshot():
    return {'orders': Order.objects.count(), 'lines': OrderLine.objects.count(), 'skus': SKU.objects.count(),
            'stock_movements': StockMovement.objects.count(),
            'money': str(Order.objects.aggregate(v=Sum('grand_total'))['v']),
            'stock': SKU.objects.aggregate(on_hand=Sum('on_hand'), reserved=Sum('reserved'))}
before = snapshot()
call_command('seed_demo')
after = snapshot()
assert before == after, 'Repeat seed modified data.'
result = {'idempotent': True, 'before': before, 'after': after}
(root / '.runtime' / 'seed-evidence.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
