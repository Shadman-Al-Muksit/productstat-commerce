"""Exact event allocations matching services.prorate's cumulative HALF_UP rule.

Allocate before filtering/grouping events so split periods, drill-down and CSV
preserve every paisa. Unknown event dates sort last; dates are never fabricated.
Event identifiers sort as text, matching SQL's explicit event-ID text ordering.
"""
from decimal import Decimal,ROUND_HALF_UP

PAISA=Decimal('0.01')

def money(value):
    rounded=Decimal(value).quantize(PAISA,rounding=ROUND_HALF_UP)
    return str(abs(rounded) if rounded==0 else rounded)

def prorate(total,event_qty,ordered_qty,previous=0):
    total=Decimal(total)
    if not total.is_finite() or total<0 or ordered_qty<=0 or event_qty<0 or previous<0 or previous+event_qty>ordered_qty:
        raise ValueError('Invalid event allocation quantities or line amount.')
    start=(total*previous/ordered_qty).quantize(PAISA,rounding=ROUND_HALF_UP)
    end=(total*(previous+event_qty)/ordered_qty).quantize(PAISA,rounding=ROUND_HALF_UP)
    return end-start

def allocate_events(line_net_total,ordered_qty,base_offset,events):
    result={};previous=base_offset
    for event_id,timestamp,quantity in sorted(events,key=lambda event:(event[1] is None,event[1],str(event[0]))):
        key=str(event_id)
        if key in result: raise ValueError('Event identifiers must be unique within a line allocation.')
        result[key]=prorate(line_net_total,quantity,ordered_qty,previous)
        previous+=quantity
    return result
