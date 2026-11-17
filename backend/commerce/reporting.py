"""Auditable merchandise activity and delivery-cohort reporting, without customer PII."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.apps import apps
from django.db import connection
from django.db.models import CharField, Count, Exists, OuterRef, Q
from django.db.models import Sum
from django.db.models.functions import Cast, Coalesce
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError
from .reporting_money import allocate_events, money as format_money, prorate

TZ = ZoneInfo("Asia/Dhaka")
ZERO = Decimal("0")
MONEY_KEYS = {"ordered_value", "delivered_value", "returned_value", "refunded_amount", "net_delivered_value"}
METRICS = {"orders", "ordered_units", "cancelled_units", "delivered_units", "returned_units", "refunds"}


def money(value):
    return format_money(value)


def filters_from_params(params):
    today = timezone.localdate(timezone.now(), TZ)
    try:
        start = date.fromisoformat(params.get("start") or (today - timedelta(days=29)).isoformat())
        end = date.fromisoformat(params.get("end") or today.isoformat())
    except (TypeError, ValueError) as exc:
        raise ValidationError("start and end must be YYYY-MM-DD dates.") from exc
    if end < start or (end - start).days > 730:
        raise ValidationError("Select an ordered date range of at most 731 days.")
    try:
        start - timedelta(days=(end - start).days + 1)
        end + timedelta(days=1)
    except OverflowError as exc:
        raise ValidationError("The date range exceeds supported calendar boundaries.") from exc
    raw_ids = params.get("product_ids", "")
    product_ids = [value.strip() for value in raw_ids.split(",") if value.strip()]
    if len(product_ids) > 20:
        raise ValidationError("Compare at most 20 products at once.")
    from uuid import UUID
    try:
        product_ids = [str(UUID(value)) for value in product_ids]
    except ValueError as exc:
        raise ValidationError("product_ids must contain product UUIDs.") from exc
    return {"start": start, "end": end, "product_ids": product_ids}


def bounds(start, end):
    return datetime.combine(start, time.min, TZ), datetime.combine(end + timedelta(days=1), time.min, TZ)


def _in_period(value, start, end):
    return value is not None and start <= value < end


def _zero_summary():
    return {"orders": 0, "ordered_units": 0, "cancelled_units": 0, "ordered_value": ZERO, "delivered_units": 0,
            "delivered_value": ZERO, "returned_units": 0, "returned_value": ZERO, "refunded_amount": ZERO,
            "net_delivered_value": ZERO}


def _serialize_summary(summary):
    return {key: money(value) if key in MONEY_KEYS else value for key, value in summary.items()}


def _unit_value(row):
    return (row["unit_price"] * row["quantity"] - row["discount_total"]) / row["quantity"]


def _line_rows(filters, earliest=None):
    Line = apps.get_model("commerce", "OrderLine")
    lo, hi = bounds(earliest or filters["start"], filters["end"])
    query = Q(order__created_at__gte=lo, order__created_at__lt=hi)
    query |= Q(delivered_at__gte=lo, delivered_at__lt=hi)
    query |= Q(returned_at__gte=lo, returned_at__lt=hi)
    query |= Q(shipment_lines__shipment__delivered_at__gte=lo, shipment_lines__shipment__delivered_at__lt=hi)
    query |= Q(shipment_lines__shipment__state="delivered", shipment_lines__shipment__completed_at__gte=lo, shipment_lines__shipment__completed_at__lt=hi)
    query |= Q(return_lines__return_request__inspected_at__gte=lo, return_lines__return_request__inspected_at__lt=hi)
    # Include old order lines refunded in the requested activity interval.
    RefundLine = apps.get_model("commerce", "RefundLine")
    refunded_ids = RefundLine.objects.filter(refund__status="confirmed", refund__confirmed_at__gte=lo,
                                             refund__confirmed_at__lt=hi, refund__order__is_current=True).values("order_line_id")
    query |= Q(id__in=refunded_ids)
    qs = Line.objects.filter(query, order__is_current=True)
    if filters["product_ids"]:
        qs = qs.filter(sku__product_id__in=filters["product_ids"])
    rows = list(qs.distinct().values("id", "sku_id", "order_id", "order__number", "order__status", "order__source",
                          "order__created_at", "sku__product_id", "sku__product__name",
                          "sku__product__category", "sku__product__image_url", "sku_code", "product_name",
                          "quantity", "cancelled_quantity", "delivered_quantity", "returned_quantity",
                          "unit_price", "discount_total", "delivered_at", "returned_at"))
    indexed = {row["id"]: row for row in rows}
    deliveries = defaultdict(list)
    returns = defaultdict(list)
    ShipmentLine = apps.get_model("commerce", "ShipmentLine")
    ReturnLine = apps.get_model("commerce", "ReturnLine")
    for event in ShipmentLine.objects.filter(order_line_id__in=indexed, shipment__state="delivered").values("id", "order_line_id", "quantity", "shipment__delivered_at", "shipment__completed_at"):
        timestamp = event["shipment__delivered_at"] or event["shipment__completed_at"]
        deliveries[event["order_line_id"]].append((str(event["id"]), timestamp, event["quantity"]))
    for event in ReturnLine.objects.filter(order_line_id__in=indexed, return_request__status="inspected", accepted_quantity__gt=0).values("id", "order_line_id", "accepted_quantity", "return_request__inspected_at"):
        returns[event["order_line_id"]].append((str(event["id"]), event["return_request__inspected_at"], event["accepted_quantity"]))
    for row in rows:
        row["_deliveries"] = sorted(deliveries[row["id"]], key=lambda item: (item[1] is None, item[1], item[0]))
        row["_returns"] = sorted(returns[row["id"]], key=lambda item: (item[1] is None, item[1], item[0]))
        # Snapshot fallback supports legacy rows; new imports/live operations create event records.
        if not any(event[1] for event in row["_deliveries"]) and row["delivered_quantity"] and row["delivered_at"]:
            row["_deliveries"] = [(str(row["id"]), row["delivered_at"], row["delivered_quantity"])]
        if not any(event[1] for event in row["_returns"]) and row["returned_quantity"] and row["returned_at"]:
            row["_returns"] = [(str(row["id"]), row["returned_at"], row["returned_quantity"])]
        total = row["unit_price"] * row["quantity"] - row["discount_total"]
        row["_delivery_values"] = allocate_events(total, row["quantity"], row["cancelled_quantity"], row["_deliveries"])
        row["_return_values"] = allocate_events(total, row["quantity"], row["cancelled_quantity"], row["_returns"])
    return rows


def _refund_rows(filters, earliest=None):
    RefundLine = apps.get_model("commerce", "RefundLine")
    lo, hi = bounds(earliest or filters["start"], filters["end"])
    qs = RefundLine.objects.filter(refund__status="confirmed", refund__confirmed_at__gte=lo,
                                   refund__confirmed_at__lt=hi, refund__order__is_current=True, order_line__order__is_current=True)
    if filters["product_ids"]:
        qs = qs.filter(order_line__sku__product_id__in=filters["product_ids"])
    rows = list(qs.values("id", "amount", "tax_amount", "shipping_amount", "refund__confirmed_at", "order_line_id", "order_line__sku_id",
                          "order_line__order__number", "order_line__order__status", "order_line__order__source",
                          "order_line__sku__product_id", "order_line__sku__product__name",
                          "order_line__sku__product__category", "order_line__sku__product__image_url",
                          "order_line__product_name", "order_line__sku_code"))
    for row in rows:
        row["amount"] -= row["tax_amount"] + row["shipping_amount"]
    return rows


def _sql_dicts(sql, params):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        names = [column[0] for column in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]


def _cancellation_rows(filters):
    """Only exact, timestamped cancellation/expiry releases; no cumulative snapshots."""
    Movement = apps.get_model("commerce", "StockMovement")
    Order = apps.get_model("commerce", "Order")
    lo, hi = bounds(filters["start"], filters["end"])
    current_orders = Order.objects.filter(is_current=True).annotate(reference_text=Cast("id", CharField())).values("reference_text")
    qs = Movement.objects.filter(kind__in=["cancel", "reservation_expired"], reserved_delta__lt=0, created_at__gte=lo, created_at__lt=hi, reference__in=current_orders)
    if filters["product_ids"]:
        qs = qs.filter(sku__product_id__in=filters["product_ids"])
    return list(qs.values("id", "sku_id", "sku__code", "sku__product_id", "sku__product__name", "reference", "reserved_delta", "created_at"))


def analytics(filters):
    """Aggregate in PostgreSQL, returning hundreds of groups rather than 75k rows.

    GROUPING SETS makes summary, daily trend and product totals use identical events.
    All runtime values remain bound parameters, including UUID filter arrays.
    """
    days = (filters["end"] - filters["start"]).days + 1
    previous_end = filters["start"] - timedelta(days=1)
    previous_start = previous_end - timedelta(days=days - 1)
    lo, hi = bounds(previous_start, filters["end"])
    split, _ = bounds(filters["start"], filters["end"])
    sql = """
        WITH cfg AS NOT MATERIALIZED (SELECT %s::timestamptz lo, %s::timestamptz hi,
                            %s::timestamptz split, %s::uuid[] products),
        selected_lines AS MATERIALIZED (
          SELECT l.id,l.order_id,s.product_id,o.created_at order_created_at,l.quantity,l.cancelled_quantity,
                 l.delivered_quantity,l.returned_quantity,l.delivered_at,l.returned_at,l.unit_price,l.discount_total
            FROM commerce_orderline l JOIN commerce_order o ON o.id=l.order_id AND o.is_current
            LEFT JOIN commerce_sku s ON s.id=l.sku_id CROSS JOIN cfg
           WHERE cardinality(cfg.products)=0 OR s.product_id=ANY(cfg.products)
        ), dated_deliveries AS MATERIALIZED (
          SELECT sl.order_line_id,sl.quantity,COALESCE(sh.delivered_at,sh.completed_at) event_at
            FROM commerce_shipmentline sl JOIN commerce_shipment sh ON sh.id=sl.shipment_id
           WHERE sh.state='delivered' AND COALESCE(sh.delivered_at,sh.completed_at) IS NOT NULL
        ), dated_returns AS MATERIALIZED (
          SELECT rl.order_line_id,rl.accepted_quantity,r.inspected_at event_at
            FROM commerce_returnline rl JOIN commerce_returnrequest r ON r.id=rl.return_request_id
           WHERE r.status='inspected' AND rl.accepted_quantity>0 AND r.inspected_at IS NOT NULL
        ), fractional_lines AS MATERIALIZED (
          SELECT l.* FROM selected_lines l
           WHERE l.discount_total>0 AND MOD((l.unit_price*l.quantity-l.discount_total)*100,l.quantity)<>0
        ), fractional_events AS (
          SELECT f.id line_id,sl.id::text event_id,COALESCE(sh.delivered_at,sh.completed_at) event_at,f.product_id,
                 'delivered' kind,sl.quantity units,f.quantity ordered_qty,f.cancelled_quantity base_qty,f.unit_price*f.quantity-f.discount_total total_value
            FROM fractional_lines f JOIN commerce_shipmentline sl ON sl.order_line_id=f.id JOIN commerce_shipment sh ON sh.id=sl.shipment_id
           WHERE sh.state='delivered' AND (COALESCE(sh.delivered_at,sh.completed_at) IS NOT NULL OR f.delivered_at IS NULL
             OR EXISTS (SELECT 1 FROM commerce_shipmentline sx JOIN commerce_shipment hx ON hx.id=sx.shipment_id
                         WHERE sx.order_line_id=f.id AND hx.state='delivered' AND COALESCE(hx.delivered_at,hx.completed_at) IS NOT NULL))
          UNION ALL
          SELECT f.id,f.id::text,f.delivered_at,f.product_id,'delivered',f.delivered_quantity,f.quantity,f.cancelled_quantity,f.unit_price*f.quantity-f.discount_total
            FROM fractional_lines f WHERE f.delivered_quantity>0 AND f.delivered_at IS NOT NULL
             AND NOT EXISTS (SELECT 1 FROM commerce_shipmentline sl JOIN commerce_shipment sh ON sh.id=sl.shipment_id
                              WHERE sl.order_line_id=f.id AND sh.state='delivered' AND COALESCE(sh.delivered_at,sh.completed_at) IS NOT NULL)
          UNION ALL
          SELECT f.id,rl.id::text,r.inspected_at,f.product_id,'returned',rl.accepted_quantity,f.quantity,f.cancelled_quantity,f.unit_price*f.quantity-f.discount_total
            FROM fractional_lines f JOIN commerce_returnline rl ON rl.order_line_id=f.id JOIN commerce_returnrequest r ON r.id=rl.return_request_id
           WHERE r.status='inspected' AND rl.accepted_quantity>0 AND (r.inspected_at IS NOT NULL OR f.returned_at IS NULL
             OR EXISTS (SELECT 1 FROM commerce_returnline rx JOIN commerce_returnrequest hx ON hx.id=rx.return_request_id
                         WHERE rx.order_line_id=f.id AND hx.status='inspected' AND rx.accepted_quantity>0 AND hx.inspected_at IS NOT NULL))
          UNION ALL
          SELECT f.id,f.id::text,f.returned_at,f.product_id,'returned',f.returned_quantity,f.quantity,f.cancelled_quantity,f.unit_price*f.quantity-f.discount_total
            FROM fractional_lines f WHERE f.returned_quantity>0 AND f.returned_at IS NOT NULL
             AND NOT EXISTS (SELECT 1 FROM commerce_returnline rl JOIN commerce_returnrequest r ON r.id=rl.return_request_id
                              WHERE rl.order_line_id=f.id AND r.status='inspected' AND rl.accepted_quantity>0 AND r.inspected_at IS NOT NULL)
        ), fractional_sequenced AS (
          SELECT fractional_events.*,SUM(units) OVER (PARTITION BY line_id,kind ORDER BY event_at NULLS LAST,event_id ROWS UNBOUNDED PRECEDING) cumulative_qty
            FROM fractional_events
        ),
        events AS (
          SELECT l.order_created_at event_at, l.product_id, 'ordered' kind,
                 l.quantity units, l.unit_price*l.quantity-l.discount_total value
            FROM selected_lines l CROSS JOIN cfg
           WHERE l.order_created_at>=cfg.lo AND l.order_created_at<cfg.hi
          UNION ALL
          SELECT m.created_at,s.product_id,'cancelled',-m.reserved_delta,0
            FROM commerce_stockmovement m JOIN commerce_sku s ON s.id=m.sku_id
            JOIN commerce_order o ON o.id::text=m.reference AND o.is_current CROSS JOIN cfg
           WHERE m.kind IN ('cancel','reservation_expired') AND m.reserved_delta<0
             AND m.created_at>=cfg.lo AND m.created_at<cfg.hi
             AND (cardinality(cfg.products)=0 OR s.product_id=ANY(cfg.products))
          UNION ALL
          SELECT d.event_at, l.product_id,'delivered',
                 d.quantity,(l.unit_price-l.discount_total/l.quantity)*d.quantity
            FROM dated_deliveries d JOIN selected_lines l ON l.id=d.order_line_id CROSS JOIN cfg
           WHERE d.event_at>=cfg.lo AND d.event_at<cfg.hi
             AND NOT EXISTS (SELECT 1 FROM fractional_lines f WHERE f.id=l.id)
          UNION ALL
          SELECT l.delivered_at,l.product_id,'delivered',l.delivered_quantity,
                 (l.unit_price-l.discount_total/l.quantity)*l.delivered_quantity
            FROM selected_lines l CROSS JOIN cfg
           WHERE l.delivered_quantity>0 AND l.delivered_at>=cfg.lo AND l.delivered_at<cfg.hi
             AND NOT EXISTS (SELECT 1 FROM fractional_lines f WHERE f.id=l.id)
             AND l.id NOT IN (SELECT d.order_line_id FROM dated_deliveries d)
          UNION ALL
          SELECT r.event_at,l.product_id,'returned',r.accepted_quantity,
                 (l.unit_price-l.discount_total/l.quantity)*r.accepted_quantity
            FROM dated_returns r JOIN selected_lines l ON l.id=r.order_line_id CROSS JOIN cfg
           WHERE r.event_at>=cfg.lo AND r.event_at<cfg.hi
             AND NOT EXISTS (SELECT 1 FROM fractional_lines f WHERE f.id=l.id)
          UNION ALL
          SELECT l.returned_at,l.product_id,'returned',l.returned_quantity,
                 (l.unit_price-l.discount_total/l.quantity)*l.returned_quantity
            FROM selected_lines l CROSS JOIN cfg
           WHERE l.returned_quantity>0 AND l.returned_at>=cfg.lo AND l.returned_at<cfg.hi
             AND NOT EXISTS (SELECT 1 FROM fractional_lines f WHERE f.id=l.id)
             AND l.id NOT IN (SELECT r.order_line_id FROM dated_returns r)
          UNION ALL
          SELECT f.event_at,f.product_id,f.kind,f.units,
                 ROUND(f.total_value*(f.base_qty+f.cumulative_qty)/f.ordered_qty,2)
                 -ROUND(f.total_value*(f.base_qty+f.cumulative_qty-f.units)/f.ordered_qty,2)
            FROM fractional_sequenced f CROSS JOIN cfg WHERE f.event_at>=cfg.lo AND f.event_at<cfg.hi
          UNION ALL
          SELECT r.confirmed_at,l.product_id,'refunded',0,rl.amount-rl.tax_amount-rl.shipping_amount
            FROM commerce_refundline rl JOIN commerce_refund r ON r.id=rl.refund_id
            JOIN selected_lines l ON l.id=rl.order_line_id JOIN commerce_order o ON o.id=r.order_id AND o.is_current CROSS JOIN cfg
           WHERE r.status='confirmed' AND r.confirmed_at>=cfg.lo AND r.confirmed_at<cfg.hi
        ), dated AS (
          SELECT events.*, (event_at AT TIME ZONE 'Asia/Dhaka')::date event_day,
                 CASE WHEN event_at>=cfg.split THEN 'current' ELSE 'previous' END period FROM events CROSS JOIN cfg
        )
        SELECT period, GROUPING(event_day) all_days, GROUPING(product_id) all_products,event_day,product_id,
               0::bigint orders,
               COALESCE(SUM(units) FILTER (WHERE kind='ordered'),0) ordered_units,
               COALESCE(SUM(units) FILTER (WHERE kind='cancelled'),0) cancelled_units,
               COALESCE(SUM(value) FILTER (WHERE kind='ordered'),0) ordered_value,
               COALESCE(SUM(units) FILTER (WHERE kind='delivered'),0) delivered_units,
               COALESCE(SUM(value) FILTER (WHERE kind='delivered'),0) delivered_value,
               COALESCE(SUM(units) FILTER (WHERE kind='returned'),0) returned_units,
               COALESCE(SUM(value) FILTER (WHERE kind='returned'),0) returned_value,
               COALESCE(SUM(value) FILTER (WHERE kind='refunded'),0) refunded_amount
          FROM dated GROUP BY GROUPING SETS ((period),(period,event_day),(period,product_id))
    """
    groups = _sql_dicts(sql, [lo, hi, split, filters["product_ids"]])
    summaries = {"current": _zero_summary(), "previous": _zero_summary()}
    trend = {(filters["start"] + timedelta(days=n)).isoformat(): _zero_summary() for n in range(days)}
    product_groups = []
    for group in groups:
        values = {key: group[key] for key in _zero_summary() if key != "net_delivered_value"}
        values["net_delivered_value"] = values["delivered_value"] - values["returned_value"]
        if group["all_days"] and group["all_products"]:
            summaries[group["period"]] = values
        elif group["period"] == "current" and group["all_products"]:
            trend[group["event_day"].isoformat()] = values
        elif group["period"] == "current" and group["all_days"]:
            product_groups.append((group["product_id"], values))
    # DISTINCT over the large mixed event stream forces sort-based grouping and
    # disk spills. Count orders separately from the smaller creation-only stream;
    # the sum-only grouping above can use bounded in-memory hash aggregation.
    order_sql = """
      WITH cfg AS NOT MATERIALIZED (SELECT %s::timestamptz lo,%s::timestamptz hi,%s::timestamptz split,%s::uuid[] products),
      ordered AS MATERIALIZED (
        SELECT o.id,(o.created_at AT TIME ZONE 'Asia/Dhaka')::date event_day,
               CASE WHEN o.created_at>=cfg.split THEN 'current' ELSE 'previous' END period
          FROM commerce_order o CROSS JOIN cfg
         WHERE o.is_current AND o.created_at>=cfg.lo AND o.created_at<cfg.hi
           AND EXISTS (SELECT 1 FROM commerce_orderline l LEFT JOIN commerce_sku s ON s.id=l.sku_id
                        WHERE l.order_id=o.id AND (cardinality(cfg.products)=0 OR s.product_id=ANY(cfg.products)))
      ), product_orders AS (
        SELECT DISTINCT o.period,s.product_id,o.id FROM ordered o JOIN commerce_orderline l ON l.order_id=o.id
          LEFT JOIN commerce_sku s ON s.id=l.sku_id CROSS JOIN cfg
         WHERE cardinality(cfg.products)=0 OR s.product_id=ANY(cfg.products)
      )
      SELECT period,'summary' dimension,NULL::date event_day,NULL::uuid product_id,COUNT(*) orders FROM ordered GROUP BY period
      UNION ALL
      SELECT period,'day',event_day,NULL::uuid,COUNT(*) FROM ordered GROUP BY period,event_day
      UNION ALL
      SELECT period,'product',NULL::date,product_id,COUNT(*) FROM product_orders GROUP BY period,product_id
    """
    product_counts = {}
    for group in _sql_dicts(order_sql, [lo, hi, split, filters["product_ids"]]):
        if group["dimension"] == "summary":
            summaries[group["period"]]["orders"] = group["orders"]
        elif group["period"] == "current" and group["dimension"] == "day":
            trend[group["event_day"].isoformat()]["orders"] = group["orders"]
        elif group["period"] == "current" and group["dimension"] == "product":
            product_counts[group["product_id"]] = group["orders"]
    for product_id, values in product_groups:
        values["orders"] = product_counts.get(product_id, 0)
    Product = apps.get_model("commerce", "Product")
    metadata = {product["id"]: product for product in Product.objects.filter(id__in=[key for key, _ in product_groups if key]).values("id", "name", "category", "image_url")}
    products = []
    for product_id, values in product_groups:
        product = metadata.get(product_id, {"name": "Archived product", "category": "", "image_url": ""})
        products.append({"id": str(product_id) if product_id else None, "name": product["name"], "category": product["category"],
                         "image_url": product["image_url"], **_serialize_summary(values)})
    products.sort(key=lambda product: Decimal(product["delivered_value"]), reverse=True)
    current, previous = summaries["current"], summaries["previous"]
    changes = {key: round(float((Decimal(current[key]) - Decimal(previous[key])) / Decimal(previous[key]) * 100), 2)
               if previous[key] else None for key in current}
    return {"filters": {"start": filters["start"].isoformat(), "end": filters["end"].isoformat(), "timezone": str(TZ),
                        "product_ids": filters["product_ids"], "currency": "BDT"},
            "summary": _serialize_summary(current), "cohort": delivery_cohort(filters),
            "cash": cash_activity(filters), "delivery": delivery_activity(filters), "return_reasons": return_reason_activity(filters), "coverage": reporting_coverage(filters),
            "comparison": {"start": previous_start.isoformat(), "end": previous_end.isoformat(),
                           "summary": _serialize_summary(previous), "change_percent": changes},
            "trend": [{"date": day, **_serialize_summary(values)} for day, values in trend.items()], "products": products,
            "meta": {"generated_at": timezone.now().isoformat(), "customer_data": "Excluded",
                     "basis": "Activity uses each event date; return cohort follows deliveries in the selected period, observed to date.",
                     "money_basis": "Delivered merchandise minus accepted returned merchandise at inspection; cash refunds separate. Excludes shipping/tax; not accounting profit.",
                     "cancellation_basis": "Observed cancellation/expiry reservation-release events only; undated historical cancellation snapshots are excluded."}}


def delivery_cohort(filters):
    lo, hi = bounds(filters["start"], filters["end"])
    Company = apps.get_model("commerce", "CompanySettings")
    window = Company.objects.values_list("return_window_days", flat=True).first() or 7
    now = timezone.now()
    # Return eligibility is inclusive Bangladesh calendar days, not elapsed hours.
    first_open_day = timezone.localdate(now, TZ) - timedelta(days=window)
    maturity = datetime.combine(first_open_day, time.min, TZ)
    sql = """
      WITH cfg AS NOT MATERIALIZED (SELECT %s::timestamptz lo,%s::timestamptz hi,%s::timestamptz as_of,
                          %s::timestamptz maturity,%s::uuid[] products),
      selected_lines AS MATERIALIZED (
        SELECT l.id,l.delivered_quantity,l.delivered_at,l.returned_quantity,l.returned_at
          FROM commerce_orderline l JOIN commerce_order o ON o.id=l.order_id AND o.is_current
          LEFT JOIN commerce_sku s ON s.id=l.sku_id CROSS JOIN cfg
         WHERE cardinality(cfg.products)=0 OR s.product_id=ANY(cfg.products)
      ), dated_deliveries AS MATERIALIZED (
        SELECT sl.id::text event_id,sl.order_line_id line_id,sl.quantity qty,COALESCE(sh.delivered_at,sh.completed_at) event_at
          FROM commerce_shipmentline sl JOIN commerce_shipment sh ON sh.id=sl.shipment_id
          JOIN selected_lines l ON l.id=sl.order_line_id
         WHERE sh.state='delivered' AND COALESCE(sh.delivered_at,sh.completed_at) IS NOT NULL
      ), deliveries AS (
        SELECT d.* FROM dated_deliveries d CROSS JOIN cfg WHERE d.event_at<=cfg.as_of AND d.event_at<cfg.hi
        UNION ALL
        SELECT l.id::text,l.id,l.delivered_quantity,l.delivered_at FROM selected_lines l CROSS JOIN cfg
         WHERE l.delivered_quantity>0 AND l.delivered_at<=cfg.as_of AND l.delivered_at<cfg.hi
           AND l.id NOT IN (SELECT d.line_id FROM dated_deliveries d)
      ), sequenced AS (
        SELECT deliveries.*,SUM(qty) OVER (PARTITION BY line_id ORDER BY event_at NULLS LAST,event_id ROWS UNBOUNDED PRECEDING)-qty prior_qty FROM deliveries
      ), cohort AS MATERIALIZED (
        SELECT d.* FROM sequenced d CROSS JOIN cfg WHERE d.event_at>=cfg.lo AND d.event_at<cfg.hi
      ), cohort_lines AS MATERIALIZED (
        SELECT DISTINCT line_id FROM cohort
      ), dated_returns AS MATERIALIZED (
        SELECT rl.order_line_id line_id,rl.accepted_quantity qty,r.inspected_at event_at
          FROM commerce_returnline rl JOIN commerce_returnrequest r ON r.id=rl.return_request_id
          JOIN commerce_order o ON o.id=r.order_id AND o.is_current JOIN cohort_lines c ON c.line_id=rl.order_line_id
         WHERE r.status='inspected' AND rl.accepted_quantity>0 AND r.inspected_at IS NOT NULL
      ), returned AS (
        SELECT r.line_id,SUM(r.qty) qty FROM dated_returns r CROSS JOIN cfg WHERE r.event_at<=cfg.as_of GROUP BY r.line_id
        UNION ALL
        SELECT l.id,l.returned_quantity FROM selected_lines l JOIN cohort_lines c ON c.line_id=l.id CROSS JOIN cfg
         WHERE l.returned_quantity>0 AND l.returned_at<=cfg.as_of
           AND l.id NOT IN (SELECT r.line_id FROM dated_returns r)
      )
      SELECT COALESCE(SUM(d.qty),0) delivered_units,
             COALESCE(SUM(LEAST(d.qty,GREATEST(0,COALESCE(r.qty,0)-d.prior_qty))),0) returned_units,
             COALESCE(SUM(d.qty) FILTER (WHERE d.event_at>=cfg.maturity),0) open_window_units,
             (SELECT COUNT(DISTINCT rr.id)
                FROM commerce_returnrequest rr JOIN commerce_returnline rl ON rl.return_request_id=rr.id JOIN cohort_lines c ON c.line_id=rl.order_line_id
                JOIN commerce_order pending_order ON pending_order.id=rr.order_id AND pending_order.is_current CROSS JOIN cfg pending_cfg
               WHERE rr.status IN ('requested','approved','received') AND rr.created_at<=pending_cfg.as_of
             ) unresolved_cases
        FROM cohort d LEFT JOIN returned r ON r.line_id=d.line_id CROSS JOIN cfg
    """
    row = _sql_dicts(sql, [lo, hi, now, maturity, filters["product_ids"]])[0]
    result = {key: int(value) for key, value in row.items()}
    result.update(return_rate=round(result["returned_units"] / result["delivered_units"] * 100, 2) if result["delivered_units"] else None,
                  preliminary=bool(result["open_window_units"] or result["unresolved_cases"]), as_of=now.isoformat(),
                  basis="Delivered units in the selected interval, accepted returns observed to date; split deliveries allocate accepted returns FIFO. Preliminary while return windows remain open or linked return cases are unresolved.")
    return result


def variant_analytics(product_id, filters):
    """Small, single-product event view grouped by immutable SKU identities."""
    Product = apps.get_model("commerce", "Product")
    SKU = apps.get_model("commerce", "SKU")
    product = Product.objects.filter(pk=product_id).values("id", "name").first()
    if product is None:
        raise NotFound("Product not found.")
    filters = {**filters, "product_ids": [str(product["id"])]}
    lo, hi = bounds(filters["start"], filters["end"])
    results = {}
    for sku in SKU.objects.filter(product_id=product_id).order_by("code", "id").values("id", "code", "label", "is_active"):
        results[sku["id"]] = {"sku_id": str(sku["id"]), "code": sku["code"], "label": sku["label"], "is_active": sku["is_active"],
                               "ordered_units": 0, "cancelled_units": 0, "delivered_units": 0, "returned_units": 0,
                               "delivered_value": ZERO, "returned_value": ZERO, "refunded_amount": ZERO, "net_delivered_value": ZERO}
    for row in _line_rows(filters):
        target = results.get(row["sku_id"])
        if target is None:
            continue
        if _in_period(row["order__created_at"], lo, hi):
            target["ordered_units"] += row["quantity"]
        for event_id, timestamp, quantity in row["_deliveries"]:
            if _in_period(timestamp, lo, hi):
                target["delivered_units"] += quantity
                target["delivered_value"] += row["_delivery_values"][event_id]
        for event_id, timestamp, quantity in row["_returns"]:
            if _in_period(timestamp, lo, hi):
                target["returned_units"] += quantity
                target["returned_value"] += row["_return_values"][event_id]
    for row in _cancellation_rows(filters):
        target = results.get(row["sku_id"])
        if target is not None:
            target["cancelled_units"] -= row["reserved_delta"]
    for row in _refund_rows(filters):
        target = results.get(row["order_line__sku_id"])
        if target is not None:
            target["refunded_amount"] += row["amount"]
    for row in results.values():
        row["net_delivered_value"] = row["delivered_value"] - row["returned_value"]
    return {"product": {"id": str(product["id"]), "name": product["name"]},
            "filters": {"start": filters["start"].isoformat(), "end": filters["end"].isoformat(), "timezone": str(TZ),
                        "currency": "BDT", "product_id": str(product["id"])},
            "results": [{key: money(value) if key in MONEY_KEYS else value for key, value in row.items()} for row in results.values()]}


def drilldown(filters, metric):
    if metric not in METRICS:
        raise ValidationError({"metric": "Choose orders, ordered_units, cancelled_units, delivered_units, returned_units or refunds."})
    lo, hi = bounds(filters["start"], filters["end"])
    rows = []
    if metric == "cancelled_units":
        Order = apps.get_model("commerce", "Order")
        events = _cancellation_rows(filters)
        from uuid import UUID
        references = []
        for event in events:
            try:
                references.append(UUID(event["reference"]))
            except ValueError:
                continue
        orders = {str(order["id"]): order for order in Order.objects.filter(id__in=references, is_current=True).values("id", "number", "status", "source")}
        Line = apps.get_model("commerce", "OrderLine")
        lines = {(str(line["order_id"]), line["sku_id"]): line for line in Line.objects.filter(order_id__in=references, order__is_current=True).values(
            "order_id", "sku_id", "sku_code", "product_name", "unit_price", "quantity", "discount_total")}
        Movement = apps.get_model("commerce", "StockMovement")
        all_releases = Movement.objects.filter(reference__in=[str(value) for value in references], kind__in=["cancel", "reservation_expired"], reserved_delta__lt=0).values(
            "id", "reference", "sku_id", "reserved_delta", "created_at")
        release_groups = defaultdict(list)
        for release in all_releases:
            release_groups[(release["reference"], release["sku_id"])].append((str(release["id"]), release["created_at"], -release["reserved_delta"]))
        release_values = {}
        for identity, release_events in release_groups.items():
            line = lines.get(identity)
            if line:
                total = line["unit_price"] * line["quantity"] - line["discount_total"]
                release_values.update(allocate_events(total, line["quantity"], 0, release_events))
        for row in events:
            order = orders.get(row["reference"], {})
            line = lines.get((row["reference"], row["sku_id"]))
            rows.append({"id": str(row["id"]), "order_number": order.get("number", row["reference"]),
                         "product_id": str(row["sku__product_id"]), "product_name": line["product_name"] if line else row["sku__product__name"], "sku": line["sku_code"] if line else row["sku__code"],
                         "quantity": -row["reserved_delta"], "value": money(release_values[str(row["id"])]) if str(row["id"]) in release_values else None, "event_at": row["created_at"].isoformat(),
                         "status": order.get("status", "cancelled"), "source": order.get("source", "live")})
    elif metric == "refunds":
        for row in _refund_rows(filters):
            rows.append({"id": str(row["id"]), "order_number": row["order_line__order__number"],
                         "product_id": str(row["order_line__sku__product_id"]) if row["order_line__sku__product_id"] else None,
                         "product_name": row["order_line__product_name"], "sku": row["order_line__sku_code"],
                         "quantity": None, "value": money(row["amount"]), "event_at": row["refund__confirmed_at"].isoformat(),
                         "status": row["order_line__order__status"], "source": row["order_line__order__source"]})
    else:
        for row in _line_rows(filters):
            events = [(str(row["id"]), row["order__created_at"], row["quantity"])] if metric in {"orders", "ordered_units"} else row["_deliveries"] if metric == "delivered_units" else row["_returns"]
            for event_id, timestamp, quantity in events:
                if not _in_period(timestamp, lo, hi) or not quantity:
                    continue
                rows.append({"id": event_id, "order_number": row["order__number"],
                             "product_id": str(row["sku__product_id"]) if row["sku__product_id"] else None,
                             "product_name": row["product_name"], "sku": row["sku_code"], "quantity": quantity,
                             "value": money(row["_delivery_values"][event_id] if metric == "delivered_units" else row["_return_values"][event_id] if metric == "returned_units" else row["unit_price"]*row["quantity"]-row["discount_total"]), "event_at": timestamp.isoformat(),
                             "status": row["order__status"], "source": row["order__source"]})
    return sorted(rows, key=lambda row: (row["event_at"], row["id"]), reverse=True)


def cash_activity(filters):
    Payment = apps.get_model("commerce", "Payment")
    PaymentSettlement = apps.get_model("commerce", "PaymentSettlement")
    Refund = apps.get_model("commerce", "Refund")
    lo, hi = bounds(filters["start"], filters["end"])
    collected = Payment.objects.filter(order__is_current=True, status__in=["successful", "exception"], collected_at__gte=lo, collected_at__lt=hi)
    settled = PaymentSettlement.objects.filter(payment__order__is_current=True, settled_at__gte=lo, settled_at__lt=hi)
    receipts = collected.aggregate(total=Sum("amount"), cod=Sum("amount", filter=Q(method="cod")),
                                   exceptions=Sum("amount", filter=Q(status="exception")), sandbox=Sum("amount", filter=Q(is_sandbox=True)))
    total = receipts["total"] or ZERO
    cod = receipts["cod"] or ZERO
    settlement = settled.aggregate(value=Sum("amount"))["value"] or ZERO
    exceptions = receipts["exceptions"] or ZERO
    sandbox = receipts["sandbox"] or ZERO
    refunded = Refund.objects.filter(order__is_current=True, status="confirmed", confirmed_at__gte=lo, confirmed_at__lt=hi).aggregate(value=Sum("amount"))["value"] or ZERO
    return {"scope": "company", "product_filter_applied": False, "collected_amount": money(total),
            "cod_collected_amount": money(cod), "online_collected_amount": money(total - cod),
            "settled_amount": money(settlement), "refunded_amount": money(refunded), "exception_collected_amount": money(exceptions), "sandbox_collected_amount": money(sandbox),
            "basis": "Recorded collection dates and individual settlement event dates, includes shipping and tax; always company-wide. Exception receipts remain refund obligations. Sandbox/demo records are not real funds."}


def return_reason_activity(filters):
    """Publish categories only: saved free text can contain customer information."""
    ReturnLine = apps.get_model("commerce", "ReturnLine")
    Line = apps.get_model("commerce", "OrderLine")
    lo, hi = bounds(filters["start"], filters["end"])
    qs = ReturnLine.objects.filter(return_request__order__is_current=True, order_line__order__is_current=True, return_request__status="inspected", accepted_quantity__gt=0,
                                    return_request__inspected_at__gte=lo, return_request__inspected_at__lt=hi)
    if filters["product_ids"]:
        qs = qs.filter(order_line__sku__product_id__in=filters["product_ids"])
    # Exact normalized matches to the storefront's codes/labels and seed category.
    # Never use substring matching: a reason can append a private name or phone.
    categories = {
        "wrong_item": "Wrong item received", "wrong item received": "Wrong item received",
        "damaged": "Damaged item", "damaged item": "Damaged item",
        "quality": "Quality concern", "quality concern": "Quality concern",
        "changed_mind": "Changed my mind", "changed my mind": "Changed my mind",
        "size or preference": "Size or preference", "synthetic: size or preference": "Size or preference",
    }
    grouped = {}
    for row in qs.values("return_request__reason").annotate(units=Sum("accepted_quantity"), count=Count("return_request_id", distinct=True)):
        reason = categories.get((row["return_request__reason"] or "").strip().casefold(), "Other/unspecified")
        target = grouped.setdefault(reason, {"reason": reason, "units": 0, "count": 0})
        target["units"] += row["units"]
        # Each case has one saved reason, so disjoint source groups can be added.
        target["count"] += row["count"]
    rows = list(grouped.values())
    observed = ReturnLine.objects.filter(order_line_id=OuterRef("pk"), return_request__status="inspected", accepted_quantity__gt=0, return_request__inspected_at__isnull=False)
    legacy = Line.objects.filter(order__is_current=True, returned_quantity__gt=0, returned_at__gte=lo, returned_at__lt=hi).annotate(observed=Exists(observed)).filter(observed=False)
    if filters["product_ids"]:
        legacy = legacy.filter(sku__product_id__in=filters["product_ids"])
    unknown_units = legacy.aggregate(units=Sum("returned_quantity"))["units"] or 0
    if unknown_units:
        rows.append({"reason": "Unknown (legacy snapshot; case count unavailable)", "units": unknown_units, "count": None})
    return sorted(rows, key=lambda row: (-row["units"], row["reason"]))


def reporting_coverage(filters):
    """Undated facts cannot be assigned to a date filter; disclose all-current scope."""
    sql = """
      WITH cfg AS NOT MATERIALIZED (SELECT %s::uuid[] products), dated_deliveries AS (
        SELECT sl.order_line_id,SUM(sl.quantity) qty FROM commerce_shipmentline sl
          JOIN commerce_shipment sh ON sh.id=sl.shipment_id
         WHERE sh.state='delivered' AND COALESCE(sh.delivered_at,sh.completed_at) IS NOT NULL GROUP BY sl.order_line_id
      ), dated_returns AS (
        SELECT rl.order_line_id,SUM(rl.accepted_quantity) qty FROM commerce_returnline rl
          JOIN commerce_returnrequest r ON r.id=rl.return_request_id
         WHERE r.status='inspected' AND rl.accepted_quantity>0 AND r.inspected_at IS NOT NULL GROUP BY rl.order_line_id
      )
      SELECT COALESCE(SUM(l.quantity) FILTER (WHERE o.created_at IS NULL),0) missing_order_date_units,
             COALESCE(SUM(GREATEST(0,l.delivered_quantity-CASE WHEN COALESCE(d.qty,0)>0 THEN d.qty
                        WHEN l.delivered_at IS NOT NULL THEN l.delivered_quantity ELSE 0 END)),0) missing_delivery_date_units,
             COALESCE(SUM(GREATEST(0,l.returned_quantity-CASE WHEN COALESCE(r.qty,0)>0 THEN r.qty
                        WHEN l.returned_at IS NOT NULL THEN l.returned_quantity ELSE 0 END)),0) missing_return_date_units,
             COALESCE(SUM(l.cancelled_quantity),0) cancelled_snapshot_units
        FROM commerce_orderline l JOIN commerce_order o ON o.id=l.order_id AND o.is_current
        LEFT JOIN commerce_sku s ON s.id=l.sku_id
        LEFT JOIN dated_deliveries d ON d.order_line_id=l.id LEFT JOIN dated_returns r ON r.order_line_id=l.id CROSS JOIN cfg
       WHERE cardinality(cfg.products)=0 OR s.product_id=ANY(cfg.products)
    """
    row = _sql_dicts(sql, [filters["product_ids"]])[0]
    Movement = apps.get_model("commerce", "StockMovement")
    Order = apps.get_model("commerce", "Order")
    Payment = apps.get_model("commerce", "Payment")
    PaymentSettlement = apps.get_model("commerce", "PaymentSettlement")
    Refund = apps.get_model("commerce", "Refund")
    refs = Order.objects.filter(is_current=True).annotate(reference_text=Cast("id", CharField())).values("reference_text")
    releases = Movement.objects.filter(kind__in=["cancel", "reservation_expired"], reserved_delta__lt=0, reference__in=refs)
    if filters["product_ids"]:
        releases = releases.filter(sku__product_id__in=filters["product_ids"])
    observed_cancelled = -(releases.aggregate(value=Sum("reserved_delta"))["value"] or 0)
    undated_collections = Payment.objects.filter(order__is_current=True, status__in=["successful", "exception"], collected_at__isnull=True).aggregate(value=Sum("amount"))["value"] or ZERO
    undated_settlements = PaymentSettlement.objects.filter(payment__order__is_current=True, settled_at__isnull=True).aggregate(value=Sum("amount"))["value"] or ZERO
    undated_refunds = Refund.objects.filter(order__is_current=True, status="confirmed", confirmed_at__isnull=True).aggregate(value=Sum("amount"))["value"] or ZERO
    return {"missing_order_date_units": int(row["missing_order_date_units"]),
            "missing_delivery_date_units": int(row["missing_delivery_date_units"]),
            "missing_return_date_units": int(row["missing_return_date_units"]),
            "cancelled_units_without_dated_event": max(0, int(row["cancelled_snapshot_units"]) - observed_cancelled),
            "undated_collection_amount": money(undated_collections), "undated_settlement_amount": money(undated_settlements),
            "undated_refund_amount": money(undated_refunds),
            "basis": "All matching current history, not the selected interval; unknown dates are excluded from dated metrics. Unit counts follow product filters; monetary coverage is company-wide."}


def delivery_activity(filters):
    Shipment = apps.get_model("commerce", "Shipment")
    lo, hi = bounds(filters["start"], filters["end"])
    qs = Shipment.objects.annotate(terminal_at=Coalesce("completed_at", "delivered_at")).filter(order__is_current=True,
        state__in=["delivered", "failed", "returned_to_origin"], terminal_at__gte=lo, terminal_at__lt=hi)
    if filters["product_ids"]:
        qs = qs.filter(lines__order_line__sku__product_id__in=filters["product_ids"])
    states = list(qs.values_list("id", "state").distinct())
    delivered = sum(state == "delivered" for _, state in states)
    failed = sum(state == "failed" for _, state in states)
    rto = sum(state == "returned_to_origin" for _, state in states)
    return {"delivered_shipments": delivered, "failed_shipments": failed, "returned_to_origin_shipments": rto,
            "terminal_shipments": len(states), "success_rate": round(delivered / len(states) * 100, 2) if states else None,
            "basis": "Delivered / (delivered + failed + returned to origin), terminal event date. Pending shipments excluded."}
