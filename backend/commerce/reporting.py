"""Auditable merchandise activity and delivery-cohort reporting, without customer PII."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.apps import apps
from django.db import connection
from django.db.models import Q
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import ValidationError

TZ = ZoneInfo("Asia/Dhaka")
ZERO = Decimal("0")
MONEY_KEYS = {"ordered_value", "delivered_value", "refunded_amount", "net_delivered_value"}
METRICS = {"orders", "ordered_units", "delivered_units", "returned_units", "refunds"}


def money(value):
    return str(Decimal(value).quantize(Decimal("0.01")))


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
    return {"orders": 0, "ordered_units": 0, "ordered_value": ZERO, "delivered_units": 0,
            "delivered_value": ZERO, "returned_units": 0, "refunded_amount": ZERO,
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
    query |= Q(return_lines__return_request__inspected_at__gte=lo, return_lines__return_request__inspected_at__lt=hi)
    # Include old order lines refunded in the requested activity interval.
    RefundLine = apps.get_model("commerce", "RefundLine")
    refunded_ids = RefundLine.objects.filter(refund__status="confirmed", refund__confirmed_at__gte=lo,
                                             refund__confirmed_at__lt=hi).values("order_line_id")
    query |= Q(id__in=refunded_ids)
    qs = Line.objects.filter(query)
    if filters["product_ids"]:
        qs = qs.filter(sku__product_id__in=filters["product_ids"])
    rows = list(qs.distinct().values("id", "order_id", "order__number", "order__status", "order__source",
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
        if timestamp:
            deliveries[event["order_line_id"]].append((str(event["id"]), timestamp, event["quantity"]))
    for event in ReturnLine.objects.filter(order_line_id__in=indexed, return_request__status="inspected", accepted_quantity__gt=0).values("id", "order_line_id", "accepted_quantity", "return_request__inspected_at"):
        if event["return_request__inspected_at"]:
            returns[event["order_line_id"]].append((str(event["id"]), event["return_request__inspected_at"], event["accepted_quantity"]))
    for row in rows:
        row["_deliveries"] = sorted(deliveries[row["id"]], key=lambda item: item[1])
        row["_returns"] = sorted(returns[row["id"]], key=lambda item: item[1])
        # Snapshot fallback supports legacy rows; new imports/live operations create event records.
        if not row["_deliveries"] and row["delivered_quantity"] and row["delivered_at"]:
            row["_deliveries"] = [(str(row["id"]), row["delivered_at"], row["delivered_quantity"])]
        if not row["_returns"] and row["returned_quantity"] and row["returned_at"]:
            row["_returns"] = [(str(row["id"]), row["returned_at"], row["returned_quantity"])]
    return rows


def _refund_rows(filters, earliest=None):
    RefundLine = apps.get_model("commerce", "RefundLine")
    lo, hi = bounds(earliest or filters["start"], filters["end"])
    qs = RefundLine.objects.filter(refund__status="confirmed", refund__confirmed_at__gte=lo,
                                   refund__confirmed_at__lt=hi)
    if filters["product_ids"]:
        qs = qs.filter(order_line__sku__product_id__in=filters["product_ids"])
    rows = list(qs.values("id", "amount", "tax_amount", "shipping_amount", "refund__confirmed_at", "order_line_id",
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
        WITH cfg AS (SELECT %s::timestamptz lo, %s::timestamptz hi,
                            %s::timestamptz split, %s::uuid[] products),
        events AS (
          SELECT o.created_at event_at, s.product_id, o.id order_id, 'ordered' kind,
                 l.quantity units, l.unit_price*l.quantity-l.discount_total value
            FROM commerce_orderline l JOIN commerce_order o ON o.id=l.order_id
            LEFT JOIN commerce_sku s ON s.id=l.sku_id CROSS JOIN cfg
           WHERE o.created_at>=cfg.lo AND o.created_at<cfg.hi
             AND (cardinality(cfg.products)=0 OR s.product_id=ANY(cfg.products))
          UNION ALL
          SELECT COALESCE(sh.delivered_at,sh.completed_at), s.product_id,l.order_id,'delivered',
                 sl.quantity,(l.unit_price-l.discount_total/l.quantity)*sl.quantity
            FROM commerce_shipmentline sl JOIN commerce_shipment sh ON sh.id=sl.shipment_id
            JOIN commerce_orderline l ON l.id=sl.order_line_id
            LEFT JOIN commerce_sku s ON s.id=l.sku_id CROSS JOIN cfg
           WHERE sh.state='delivered' AND COALESCE(sh.delivered_at,sh.completed_at)>=cfg.lo
             AND COALESCE(sh.delivered_at,sh.completed_at)<cfg.hi
             AND (cardinality(cfg.products)=0 OR s.product_id=ANY(cfg.products))
          UNION ALL
          SELECT l.delivered_at,s.product_id,l.order_id,'delivered',l.delivered_quantity,
                 (l.unit_price-l.discount_total/l.quantity)*l.delivered_quantity
            FROM commerce_orderline l LEFT JOIN commerce_sku s ON s.id=l.sku_id CROSS JOIN cfg
           WHERE l.delivered_quantity>0 AND l.delivered_at>=cfg.lo AND l.delivered_at<cfg.hi
             AND NOT EXISTS (SELECT 1 FROM commerce_shipmentline sl JOIN commerce_shipment sh ON sh.id=sl.shipment_id
                              WHERE sl.order_line_id=l.id AND sh.state='delivered' AND COALESCE(sh.delivered_at,sh.completed_at) IS NOT NULL)
             AND (cardinality(cfg.products)=0 OR s.product_id=ANY(cfg.products))
          UNION ALL
          SELECT r.inspected_at,s.product_id,l.order_id,'returned',rl.accepted_quantity,0
            FROM commerce_returnline rl JOIN commerce_returnrequest r ON r.id=rl.return_request_id
            JOIN commerce_orderline l ON l.id=rl.order_line_id LEFT JOIN commerce_sku s ON s.id=l.sku_id CROSS JOIN cfg
           WHERE r.status='inspected' AND rl.accepted_quantity>0 AND r.inspected_at>=cfg.lo AND r.inspected_at<cfg.hi
             AND (cardinality(cfg.products)=0 OR s.product_id=ANY(cfg.products))
          UNION ALL
          SELECT l.returned_at,s.product_id,l.order_id,'returned',l.returned_quantity,0
            FROM commerce_orderline l LEFT JOIN commerce_sku s ON s.id=l.sku_id CROSS JOIN cfg
           WHERE l.returned_quantity>0 AND l.returned_at>=cfg.lo AND l.returned_at<cfg.hi
             AND NOT EXISTS (SELECT 1 FROM commerce_returnline rl JOIN commerce_returnrequest r ON r.id=rl.return_request_id
                              WHERE rl.order_line_id=l.id AND r.status='inspected' AND rl.accepted_quantity>0 AND r.inspected_at IS NOT NULL)
             AND (cardinality(cfg.products)=0 OR s.product_id=ANY(cfg.products))
          UNION ALL
          SELECT r.confirmed_at,s.product_id,l.order_id,'refunded',0,rl.amount-rl.tax_amount-rl.shipping_amount
            FROM commerce_refundline rl JOIN commerce_refund r ON r.id=rl.refund_id
            JOIN commerce_orderline l ON l.id=rl.order_line_id LEFT JOIN commerce_sku s ON s.id=l.sku_id CROSS JOIN cfg
           WHERE r.status='confirmed' AND r.confirmed_at>=cfg.lo AND r.confirmed_at<cfg.hi
             AND (cardinality(cfg.products)=0 OR s.product_id=ANY(cfg.products))
        ), dated AS (
          SELECT events.*, (event_at AT TIME ZONE 'Asia/Dhaka')::date event_day,
                 CASE WHEN event_at>=cfg.split THEN 'current' ELSE 'previous' END period FROM events CROSS JOIN cfg
        )
        SELECT period, GROUPING(event_day) all_days, GROUPING(product_id) all_products,event_day,product_id,
               COUNT(DISTINCT order_id) FILTER (WHERE kind='ordered') orders,
               COALESCE(SUM(units) FILTER (WHERE kind='ordered'),0) ordered_units,
               COALESCE(SUM(value) FILTER (WHERE kind='ordered'),0) ordered_value,
               COALESCE(SUM(units) FILTER (WHERE kind='delivered'),0) delivered_units,
               COALESCE(SUM(value) FILTER (WHERE kind='delivered'),0) delivered_value,
               COALESCE(SUM(units) FILTER (WHERE kind='returned'),0) returned_units,
               COALESCE(SUM(value) FILTER (WHERE kind='refunded'),0) refunded_amount
          FROM dated GROUP BY GROUPING SETS ((period),(period,event_day),(period,product_id))
    """
    groups = _sql_dicts(sql, [lo, hi, split, filters["product_ids"]])
    summaries = {"current": _zero_summary(), "previous": _zero_summary()}
    trend = {(filters["start"] + timedelta(days=n)).isoformat(): _zero_summary() for n in range(days)}
    product_groups = []
    for group in groups:
        values = {key: group[key] for key in _zero_summary() if key != "net_delivered_value"}
        values["net_delivered_value"] = values["delivered_value"] - values["refunded_amount"]
        if group["all_days"] and group["all_products"]:
            summaries[group["period"]] = values
        elif group["period"] == "current" and group["all_products"]:
            trend[group["event_day"].isoformat()] = values
        elif group["period"] == "current" and group["all_days"]:
            product_groups.append((group["product_id"], values))
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
            "cash": cash_activity(filters), "delivery": delivery_activity(filters),
            "comparison": {"start": previous_start.isoformat(), "end": previous_end.isoformat(),
                           "summary": _serialize_summary(previous), "change_percent": changes},
            "trend": [{"date": day, **_serialize_summary(values)} for day, values in trend.items()], "products": products,
            "meta": {"generated_at": timezone.now().isoformat(), "customer_data": "Excluded",
                     "basis": "Activity uses each event date; return cohort follows deliveries in the selected period, observed to date.",
                     "money_basis": "Merchandise after discounts; excludes shipping and tax. Not accounting profit."}}


def delivery_cohort(filters):
    lo, hi = bounds(filters["start"], filters["end"])
    Company = apps.get_model("commerce", "CompanySettings")
    window = Company.objects.values_list("return_window_days", flat=True).first() or 7
    now = timezone.now()
    sql = """
      WITH cfg AS (SELECT %s::timestamptz lo,%s::timestamptz hi,%s::timestamptz as_of,
                          %s::timestamptz maturity,%s::uuid[] products),
      deliveries AS (
        SELECT sl.id::text event_id,sl.order_line_id line_id,sl.quantity qty,COALESCE(sh.delivered_at,sh.completed_at) event_at
          FROM commerce_shipmentline sl JOIN commerce_shipment sh ON sh.id=sl.shipment_id
          JOIN commerce_orderline l ON l.id=sl.order_line_id LEFT JOIN commerce_sku s ON s.id=l.sku_id CROSS JOIN cfg
         WHERE sh.state='delivered' AND COALESCE(sh.delivered_at,sh.completed_at)<=cfg.as_of
           AND (cardinality(cfg.products)=0 OR s.product_id=ANY(cfg.products))
        UNION ALL
        SELECT l.id::text,l.id,l.delivered_quantity,l.delivered_at FROM commerce_orderline l
          LEFT JOIN commerce_sku s ON s.id=l.sku_id CROSS JOIN cfg
         WHERE l.delivered_quantity>0 AND l.delivered_at<=cfg.as_of
           AND NOT EXISTS (SELECT 1 FROM commerce_shipmentline sl JOIN commerce_shipment sh ON sh.id=sl.shipment_id
                            WHERE sl.order_line_id=l.id AND sh.state='delivered' AND COALESCE(sh.delivered_at,sh.completed_at) IS NOT NULL)
           AND (cardinality(cfg.products)=0 OR s.product_id=ANY(cfg.products))
      ), returned AS (
        SELECT rl.order_line_id line_id,SUM(rl.accepted_quantity) qty FROM commerce_returnline rl
          JOIN commerce_returnrequest r ON r.id=rl.return_request_id CROSS JOIN cfg
         WHERE r.status='inspected' AND r.inspected_at<=cfg.as_of GROUP BY rl.order_line_id
        UNION ALL
        SELECT l.id,l.returned_quantity FROM commerce_orderline l CROSS JOIN cfg
         WHERE l.returned_quantity>0 AND l.returned_at<=cfg.as_of
           AND NOT EXISTS (SELECT 1 FROM commerce_returnline rl JOIN commerce_returnrequest r ON r.id=rl.return_request_id
                            WHERE rl.order_line_id=l.id AND r.status='inspected' AND rl.accepted_quantity>0 AND r.inspected_at IS NOT NULL)
      ), sequenced AS (
        SELECT deliveries.*,SUM(qty) OVER (PARTITION BY line_id ORDER BY event_at,event_id ROWS UNBOUNDED PRECEDING)-qty prior_qty FROM deliveries
      )
      SELECT COALESCE(SUM(d.qty),0) delivered_units,
             COALESCE(SUM(LEAST(d.qty,GREATEST(0,COALESCE(r.qty,0)-d.prior_qty))),0) returned_units,
             COALESCE(SUM(d.qty) FILTER (WHERE d.event_at>cfg.maturity),0) open_window_units
        FROM sequenced d LEFT JOIN returned r ON r.line_id=d.line_id CROSS JOIN cfg
       WHERE d.event_at>=cfg.lo AND d.event_at<cfg.hi
    """
    row = _sql_dicts(sql, [lo, hi, now, now - timedelta(days=window), filters["product_ids"]])[0]
    result = {key: int(value) for key, value in row.items()}
    result.update(return_rate=round(result["returned_units"] / result["delivered_units"] * 100, 2) if result["delivered_units"] else None,
                  preliminary=bool(result["open_window_units"]), as_of=now.isoformat(),
                  basis="Delivered units in the selected interval, accepted returns observed to date; split deliveries allocate accepted returns FIFO.")
    return result


def drilldown(filters, metric):
    if metric not in METRICS:
        raise ValidationError({"metric": "Choose orders, ordered_units, delivered_units, returned_units or refunds."})
    lo, hi = bounds(filters["start"], filters["end"])
    rows = []
    if metric == "refunds":
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
                             "value": money(_unit_value(row) * quantity), "event_at": timestamp.isoformat(),
                             "status": row["order__status"], "source": row["order__source"]})
    return sorted(rows, key=lambda row: (row["event_at"], row["id"]), reverse=True)


def cash_activity(filters):
    Payment = apps.get_model("commerce", "Payment")
    lo, hi = bounds(filters["start"], filters["end"])
    collected = Payment.objects.filter(status__in=["successful", "exception"], collected_at__gte=lo, collected_at__lt=hi)
    settled = Payment.objects.filter(status__in=["successful", "exception"], settled_at__gte=lo, settled_at__lt=hi)
    total = collected.aggregate(value=Sum("amount"))["value"] or ZERO
    cod = collected.filter(method="cod").aggregate(value=Sum("amount"))["value"] or ZERO
    settlement = settled.aggregate(value=Sum("settled_amount"))["value"] or ZERO
    exceptions = collected.filter(status="exception").aggregate(value=Sum("amount"))["value"] or ZERO
    sandbox = collected.filter(is_sandbox=True).aggregate(value=Sum("amount"))["value"] or ZERO
    return {"scope": "company", "product_filter_applied": False, "collected_amount": money(total),
            "cod_collected_amount": money(cod), "online_collected_amount": money(total - cod),
            "settled_amount": money(settlement), "exception_collected_amount": money(exceptions), "sandbox_collected_amount": money(sandbox),
            "basis": "Recorded cash event dates, includes shipping and tax; always company-wide. Exception receipts remain refund obligations. Sandbox/demo records are not real funds."}


def delivery_activity(filters):
    Shipment = apps.get_model("commerce", "Shipment")
    lo, hi = bounds(filters["start"], filters["end"])
    qs = Shipment.objects.annotate(terminal_at=Coalesce("completed_at", "delivered_at")).filter(
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
