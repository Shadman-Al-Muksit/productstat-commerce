"""Staged CSV ingestion. History writes snapshots and never calls live order services."""
import csv
import hashlib
import io
import json
import re
import zipfile
from collections import defaultdict
from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal, InvalidOperation
from pathlib import PurePath
from zoneinfo import ZoneInfo
from uuid import uuid4

from django.core.files.base import ContentFile
from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from django.utils.text import slugify

from .models import (AuditEvent, ImportBatch, Order, OrderLine, Payment, PaymentSettlement, Product, Refund,
                     RefundLine, ReturnLine, ReturnRequest, Shipment, ShipmentLine, SKU, StockMovement)

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 25000
TZ = ZoneInfo("Asia/Dhaka")
KINDS = {"catalog", "opening_stock", "adjustments", "history"}
SCHEMAS = {
    "catalog": ["product_slug", "product_name", "category", "description", "image_url", "sku", "variant_name", "price", "cost"],
    "opening_stock": ["source_record_id", "sku", "quantity"],
    "adjustments": ["source_record_id", "sku", "quantity_delta", "reason"],
    "history": ["source_order_id", "source_line_id", "sku", "ordered_at", "status", "payment_method", "shipping_total", "quantity", "unit_price", "discount_total", "tax_total", "cancelled_quantity", "shipped_quantity", "delivered_quantity", "delivered_at", "returned_quantity", "returned_at", "refund_amount", "refund_tax_amount", "refund_shipping_amount", "refunded_at", "collected_amount", "collected_at", "settled_amount", "settled_at"],
    "orders": ["source_order_id", "ordered_at", "status", "payment_method", "shipping_total"],
    "lines": ["source_order_id", "source_line_id", "sku", "quantity", "unit_price", "discount_total", "tax_total", "cancelled_quantity"],
    "shipments": ["source_order_id", "source_line_id", "source_shipment_id", "state", "quantity", "dispatched_at", "completed_at"],
    "returns": ["source_order_id", "source_line_id", "source_return_id", "quantity", "accepted_quantity", "received_at", "inspected_at", "disposition"],
    "refunds": ["source_order_id", "source_line_id", "source_refund_id", "amount", "tax_amount", "shipping_amount", "confirmed_at"],
    "payments": ["source_order_id", "source_payment_id", "method", "amount", "collected_at", "settled_amount", "settled_at"],
}


class ImportProblem(ValueError):
    pass


class ImportConflict(ImportProblem):
    """A stable source identity cannot silently replace different historical facts."""
    pass


def template_csv(kind):
    if kind not in SCHEMAS:
        raise ImportProblem("Unknown template kind.")
    buffer = io.StringIO()
    csv.writer(buffer).writerow(SCHEMAS[kind])
    return buffer.getvalue()


def stage_upload(*, kind, source_name, files, actor):
    if kind not in KINDS:
        raise ImportProblem("kind must be catalog, opening_stock, adjustments or history.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,69}", source_name or ""):
        raise ImportProblem("source_name must be a stable identifier of 1–70 letters, digits, dots, dashes or underscores.")
    if not files or sum(upload.size for upload in files) > MAX_BYTES:
        raise ImportProblem("Supply CSV files totalling at most 10 MB.")
    for upload in files:
        if not upload.name.lower().endswith(".csv"):
            raise ImportProblem("Only UTF-8 CSV files are accepted.")
    batch = ImportBatch(kind=kind, source_name=source_name, created_by=actor,
                        filename=", ".join(PurePath(upload.name).name for upload in files)[:250])
    if len(files) == 1:
        batch.file.save("upload.csv", ContentFile(files[0].read()), save=False)
    else:
        if kind != "history":
            raise ImportProblem("Multiple related files are supported for history imports only.")
        archive = io.BytesIO()
        names = set()
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as target:
            for upload in files:
                name = PurePath(upload.name).name.lower()
                if name in names or name.removesuffix(".csv") not in {"orders", "lines", "shipments", "returns", "refunds", "payments"}:
                    raise ImportProblem("Related files must use unique names: orders.csv, lines.csv, shipments.csv, returns.csv, refunds.csv, payments.csv.")
                names.add(name)
                target.writestr(name, upload.read())
        batch.file.save("related.zip", ContentFile(archive.getvalue()), save=False)
    batch.save()
    return batch


def read_datasets(batch):
    batch.file.open("rb")
    try:
        raw = batch.file.read(MAX_BYTES + 1)
    finally:
        batch.file.close()
    if len(raw) > MAX_BYTES:
        raise ImportProblem("Upload exceeds 10 MB.")
    if batch.file.name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if sum(info.file_size for info in archive.infolist()) > MAX_BYTES:
                raise ImportProblem("CSV content exceeds 10 MB.")
            sources = {name.removesuffix(".csv"): archive.read(name) for name in archive.namelist()}
    else:
        sources = {batch.kind: raw}
    datasets = {}
    total = 0
    for schema, payload in sources.items():
        if schema not in SCHEMAS:
            raise ImportProblem(f"Unsupported schema: {schema}.")
        try:
            reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")), strict=True)
            if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
                raise ImportProblem(f"{schema}: missing or duplicate CSV columns.")
            if any(name not in SCHEMAS[schema] for name in reader.fieldnames):
                raise ImportProblem(f"{schema}: unrecognized columns; download its template.")
            rows = []
            for line_number, row in enumerate(reader, start=2):
                if None in row or any(value is None for value in row.values()):
                    raise ImportProblem(f"{schema} row {line_number}: wrong number of fields.")
                if not any(value.strip() for value in row.values()):
                    continue
                total += 1
                if total > MAX_ROWS:
                    raise ImportProblem("An import may contain at most 25,000 data rows across all files.")
                rows.append({**{key: value.strip() for key, value in row.items()}, "_row": line_number, "_schema": schema})
            datasets[schema] = rows
        except (UnicodeDecodeError, csv.Error) as exc:
            raise ImportProblem(f"{schema}: invalid UTF-8 CSV: {exc}") from exc
    if not total:
        raise ImportProblem("The import contains no data rows.")
    return datasets


def _required(row, key):
    value = row.get(key, "")
    if not value:
        raise ImportProblem(f"{key} is required.")
    maximum = 80 if key == "sku" else 120 if key == "source_shipment_id" else 220 if key == "product_slug" else 200 if key == "product_name" else 150
    if len(value) > maximum:
        raise ImportProblem(f"{key} exceeds {maximum} characters.")
    return value


def _integer(row, key, default=None, minimum=0):
    value = row.get(key, "")
    if value == "" and default is not None:
        return default
    if len(str(value)) > 12:
        raise ImportProblem(f"{key} is too large.")
    try:
        number = int(value)
    except (ValueError, TypeError) as exc:
        raise ImportProblem(f"{key} must be an integer.") from exc
    if minimum is not None and number < minimum:
        raise ImportProblem(f"{key} must be at least {minimum}.")
    if not -2147483648 <= number <= 2147483647:
        raise ImportProblem(f"{key} exceeds the supported integer range.")
    return number


def _decimal(row, key, default="0"):
    value = row.get(key, "") or default
    if len(str(value)) > 30:
        raise ImportProblem(f"{key} is too large.")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ImportProblem(f"{key} must be a decimal amount.") from exc
    if not number.is_finite() or number < 0 or number != number.quantize(Decimal("0.01")) or number > Decimal("9999999999.99"):
        raise ImportProblem(f"{key} must be a nonnegative amount with at most two decimal places.")
    return number


def _timestamp(row, key, required=False):
    raw = row.get(key, "")
    if not raw:
        if required:
            raise ImportProblem(f"{key} is required when its quantity or amount is positive.")
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ImportProblem(f"{key} must be an ISO-8601 timestamp with an explicit timezone.") from exc
    if timezone.is_naive(value):
        raise ImportProblem(f"{key} must include its timezone offset.")
    if value > timezone.now():
        raise ImportProblem(f"{key} cannot be in the future.")
    return value


def _validate_history_line(row):
    _required(row, "source_order_id")
    _required(row, "source_line_id")
    _required(row, "sku")
    quantity = _integer(row, "quantity", minimum=1)
    cancelled = _integer(row, "cancelled_quantity", 0)
    shipped = _integer(row, "shipped_quantity", 0)
    delivered = _integer(row, "delivered_quantity", 0)
    returned = _integer(row, "returned_quantity", 0)
    price = _decimal(row, "unit_price")
    discount = _decimal(row, "discount_total")
    tax = _decimal(row, "tax_total")
    if cancelled + shipped > quantity or delivered > shipped or returned > delivered:
        raise ImportProblem("Quantities must satisfy cancelled + shipped ≤ ordered, delivered ≤ shipped, returned ≤ delivered.")
    if discount > quantity * price:
        raise ImportProblem("discount_total exceeds merchandise value.")
    ordered_at = _timestamp(row, "ordered_at")
    delivered_at = _timestamp(row, "delivered_at")
    returned_at = _timestamp(row, "returned_at")
    refund = _decimal(row, "refund_amount")
    refund_tax = _decimal(row, "refund_tax_amount")
    refund_shipping = _decimal(row, "refund_shipping_amount")
    refunded_at = _timestamp(row, "refunded_at")
    collected = _decimal(row, "collected_amount")
    collected_at = _timestamp(row, "collected_at")
    settled = _decimal(row, "settled_amount")
    settled_at = _timestamp(row, "settled_at")
    if refund_tax + refund_shipping > refund or refund_tax > tax:
        raise ImportProblem("Refund tax/shipping allocation exceeds its refund or the line tax snapshot.")
    if settled > collected or ("_payments" not in row and refund > collected) or refund - refund_tax - refund_shipping > quantity * price - discount:
        raise ImportProblem("Settlement/refund exceeds recorded collections or refund exceeds line value.")
    for label, value in [("delivered_at", delivered_at), ("returned_at", returned_at), ("refunded_at", refunded_at), ("collected_at", collected_at), ("settled_at", settled_at)]:
        if value and ordered_at and value < ordered_at:
            raise ImportProblem(f"{label} precedes ordered_at.")
    if "_returns" not in row and returned_at and delivered_at and returned_at < delivered_at:
        raise ImportProblem("returned_at precedes delivered_at.")
    if settled_at and collected_at and settled_at < collected_at:
        raise ImportProblem("settled_at precedes collected_at.")
    if refunded_at and collected_at and refunded_at < collected_at:
        raise ImportProblem("refunded_at precedes collection.")
    if row.get("status", "delivered") not in {"pending_payment", "confirmed", "preparing", "dispatched", "delivered", "failed", "returned_to_origin", "cancelled"}:
        raise ImportProblem("Unknown order status.")
    if row.get("payment_method", "cod") not in {"cod", "sslcommerz"}:
        raise ImportProblem("payment_method must be cod or sslcommerz.")


def normalize_history(datasets):
    if "history" in datasets:
        return datasets["history"]
    if not {"orders", "lines"}.issubset(datasets):
        raise ImportProblem("A related history batch requires orders.csv and lines.csv.")
    orders = {}
    for row in datasets["orders"]:
        key = _required(row, "source_order_id")
        if key in orders:
            raise ImportProblem(f"orders row {row['_row']}: duplicate source_order_id.")
        orders[key] = row
    records = {}
    order_records = defaultdict(list)
    for row in datasets["lines"]:
        key = (_required(row, "source_order_id"), _required(row, "source_line_id"))
        if key in records or key[0] not in orders:
            raise ImportProblem(f"lines row {row['_row']}: duplicate line or missing parent order.")
        records[key] = {**orders[key[0]], **row, "_shipments": [], "_returns": [], "_refunds": [], "_payments": [],
                        "shipped_quantity": "0", "delivered_quantity": "0", "returned_quantity": "0", "refund_amount": "0",
                        "refund_tax_amount": "0", "refund_shipping_amount": "0", "collected_amount": "0", "settled_amount": "0"}
        order_records[key[0]].append(records[key])
    if any(order_id not in order_records for order_id in orders):
        raise ImportProblem("Every order must have at least one line.")
    for schema in ("shipments", "returns", "refunds"):
        seen = set()
        event_metadata = {}
        for row in datasets.get(schema, []):
            key = (_required(row, "source_order_id"), _required(row, "source_line_id"))
            identifier = _required(row, f"source_{schema[:-1] if schema != 'refunds' else 'refund'}_id")
            identity = (*key, identifier)
            if identity in seen or key not in records:
                raise ImportProblem(f"{schema} row {row['_row']}: duplicate event or missing parent line.")
            seen.add(identity)
            shared_fields = {"shipments": ("state", "dispatched_at", "completed_at"),
                             "returns": ("received_at", "inspected_at"), "refunds": ("confirmed_at",)}[schema]
            shared = tuple(row.get(field, "") for field in shared_fields)
            event_key = (key[0], identifier)
            if event_key in event_metadata and event_metadata[event_key] != shared:
                raise ImportProblem(f"{schema}: inconsistent metadata for shared event {identifier}.")
            event_metadata[event_key] = shared
            target = records[key]
            target[f"_{schema}"].append(row)
            if schema == "shipments":
                qty = _integer(row, "quantity", minimum=1)
                dispatched = _timestamp(row, "dispatched_at")
                state = _required(row, "state")
                if state not in {"dispatched", "delivered", "failed", "returned_to_origin"}:
                    raise ImportProblem("Unknown shipment state.")
                completed = _timestamp(row, "completed_at")
                if completed and dispatched and completed < dispatched:
                    raise ImportProblem("Shipment completion precedes dispatch.")
                target["shipped_quantity"] = str(int(target["shipped_quantity"]) + qty)
                if state == "delivered":
                    target["delivered_quantity"] = str(int(target["delivered_quantity"]) + qty)
                    previous = _timestamp(target, "delivered_at")
                    if completed and (not previous or completed > previous):
                        target["delivered_at"] = completed.isoformat()
            elif schema == "returns":
                qty = _integer(row, "quantity", minimum=1)
                accepted = _integer(row, "accepted_quantity", 0)
                if accepted > qty:
                    raise ImportProblem("accepted_quantity exceeds requested return quantity.")
                received = _timestamp(row, "received_at")
                inspected = _timestamp(row, "inspected_at")
                if inspected and received and inspected < received:
                    raise ImportProblem("Return inspection precedes receipt.")
                if row.get("disposition", "quarantine") not in {"restock", "quarantine", "dispose"}:
                    raise ImportProblem("Unknown return disposition.")
                target["returned_quantity"] = str(int(target["returned_quantity"]) + accepted)
                if inspected:
                    previous = _timestamp(target, "returned_at")
                    if not previous or inspected > previous:
                        target["returned_at"] = inspected.isoformat()
            else:
                amount = _decimal(row, "amount")
                if not amount:
                    raise ImportProblem("A refund event requires a positive amount.")
                tax_amount = _decimal(row, "tax_amount")
                shipping_amount = _decimal(row, "shipping_amount")
                if tax_amount + shipping_amount > amount:
                    raise ImportProblem("Refund tax/shipping exceeds its total amount.")
                confirmed = _timestamp(row, "confirmed_at")
                target["refund_amount"] = str(Decimal(target["refund_amount"]) + amount)
                target["refund_tax_amount"] = str(Decimal(target["refund_tax_amount"]) + tax_amount)
                target["refund_shipping_amount"] = str(Decimal(target["refund_shipping_amount"]) + shipping_amount)
                previous = _timestamp(target, "refunded_at")
                if confirmed and (not previous or confirmed > previous):
                    target["refunded_at"] = confirmed.isoformat()
    payment_ids = set()
    for row in datasets.get("payments", []):
        order_id = _required(row, "source_order_id")
        payment_id = _required(row, "source_payment_id")
        if (order_id, payment_id) in payment_ids:
            raise ImportProblem(f"payments row {row['_row']}: duplicate source_payment_id.")
        payment_ids.add((order_id, payment_id))
        if order_id not in orders:
            raise ImportProblem("Payment references a missing order.")
        amount = _decimal(row, "amount")
        if not amount:
            raise ImportProblem("A payment event requires a positive amount.")
        settled = _decimal(row, "settled_amount")
        _timestamp(row, "collected_at")
        _timestamp(row, "settled_at")
        if settled > amount:
            raise ImportProblem("Payment settlement exceeds collection.")
        if row.get("method") not in {"cod", "sslcommerz"}:
            raise ImportProblem("Payment method must be cod or sslcommerz.")
        collected_at = _timestamp(row, "collected_at")
        settled_at = _timestamp(row, "settled_at")
        ordered_at = _timestamp(orders[order_id], "ordered_at")
        if collected_at and ordered_at and collected_at < ordered_at:
            raise ImportProblem("Collection precedes order creation.")
        if settled_at and collected_at and settled_at < collected_at:
            raise ImportProblem("Settlement precedes collection.")
        related = order_records[order_id]
        # Keep the order-level payment once, independent of line ordering.
        if related:
            related[0]["_payments"].append(row)
    return list(records.values())


def validate_history_consistency(records):
    """Check cross-line facts that cannot be validated one CSV row at a time."""
    grouped = defaultdict(list)
    for record in records:
        grouped[_required(record, "source_order_id")].append(record)
    for order_id, rows in grouped.items():
        first = rows[0]
        signature = (_timestamp(first, "ordered_at"), first.get("status"), first.get("payment_method"), _decimal(first, "shipping_total"))
        for row in rows[1:]:
            other = (_timestamp(row, "ordered_at"), row.get("status"), row.get("payment_method"), _decimal(row, "shipping_total"))
            if signature != other:
                raise ImportProblem(f"Order {order_id}: inconsistent ordered_at, status, payment_method or shipping_total across lines.")
        collected = sum((_decimal(event, "amount") for row in rows for event in row.get("_payments", [])), Decimal(0)) if "_payments" in first else sum((_decimal(row, "collected_amount") for row in rows), Decimal(0))
        refunded = sum((_decimal(row, "refund_amount") for row in rows), Decimal(0))
        shipping_refund = sum((_decimal(row, "refund_shipping_amount") for row in rows), Decimal(0))
        value = sum((_decimal(row, "unit_price") * _integer(row, "quantity", minimum=1) - _decimal(row, "discount_total") + _decimal(row, "tax_total") for row in rows), Decimal(0)) + signature[3]
        if collected > value or refunded > collected or shipping_refund > signature[3]:
            raise ImportProblem(f"Order {order_id}: collections exceed order value or refunds exceed collections/shipping charges.")
        if value > Decimal("999999999999.99"):
            raise ImportProblem(f"Order {order_id}: total exceeds the supported monetary range.")
        if signature[1] == "cancelled" and any(_integer(row, "cancelled_quantity", 0) != _integer(row, "quantity", minimum=1) for row in rows):
            raise ImportProblem(f"Order {order_id}: a cancelled order must cancel every unit.")
        if signature[1] == "delivered" and any(_integer(row, "delivered_quantity", 0) + _integer(row, "cancelled_quantity", 0) != _integer(row, "quantity", minimum=1) for row in rows):
            raise ImportProblem(f"Order {order_id}: delivered status conflicts with undelivered units.")
        if "_shipments" in first:
            for row in rows:
                ordered_at = signature[0]
                delivered_events = []
                for event in row["_shipments"]:
                    dispatched = _timestamp(event, "dispatched_at")
                    if dispatched and ordered_at and dispatched < ordered_at:
                        raise ImportProblem(f"Order {order_id}: shipment precedes order creation.")
                    if event["state"] == "delivered":
                        delivered_events.append((_timestamp(event, "completed_at"), _integer(event, "quantity", minimum=1)))
                accepted_events = [(_timestamp(event, "inspected_at"), _integer(event, "accepted_quantity", 0)) for event in row["_returns"] if _integer(event, "accepted_quantity", 0)]
                if ordered_at and any(_timestamp(event, "received_at") and _timestamp(event, "received_at") < ordered_at for event in row["_returns"]):
                    raise ImportProblem(f"Order {order_id}: return receipt precedes order creation.")
                accepted_so_far = 0
                for inspected_at, quantity in sorted(accepted_events, key=lambda event: (event[0] is None, event[0])):
                    accepted_so_far += quantity
                    delivered_so_far = sum(qty for event_at, qty in delivered_events if event_at and inspected_at and event_at <= inspected_at)
                    # An unknown date cannot establish chronology. Quantity bounds still apply.
                    if inspected_at and all(event_at for event_at, _ in delivered_events) and all(event_at for event_at, _ in accepted_events) and accepted_so_far > delivered_so_far:
                        raise ImportProblem(f"Order {order_id}: accepted returns precede sufficient deliveries.")
            cash_events = [(_timestamp(event, "collected_at"), _decimal(event, "amount")) for row in rows for event in row["_payments"] if _decimal(event, "amount")]
            refunds = sorted([(_timestamp(event, "confirmed_at"), _decimal(event, "amount")) for row in rows for event in row["_refunds"] if _decimal(event, "amount")], key=lambda event: (event[0] is None, event[0]))
            refunded_so_far = Decimal(0)
            for refund_at, amount in refunds:
                refunded_so_far += amount
                if refund_at and all(collected_at for collected_at, _ in cash_events) and all(confirmed_at for confirmed_at, _ in refunds) and refunded_so_far > sum((amount for collected_at, amount in cash_events if collected_at <= refund_at), Decimal(0)):
                    raise ImportProblem(f"Order {order_id}: refund precedes sufficient collected payment.")


MONEY_FIELDS = {"price", "cost", "unit_price", "discount_total", "tax_total", "shipping_total", "amount", "tax_amount", "shipping_amount",
                "refund_amount", "refund_tax_amount", "refund_shipping_amount", "collected_amount", "settled_amount"}
INTEGER_FIELDS = {"quantity", "cancelled_quantity", "shipped_quantity", "delivered_quantity", "returned_quantity", "accepted_quantity", "quantity_delta"}


def _canonical_value(row, field):
    if field in MONEY_FIELDS:
        return format(_decimal(row, field).quantize(Decimal("0.01")), "f")
    if field in INTEGER_FIELDS:
        return _integer(row, field, 0, minimum=None if field == "quantity_delta" else 0)
    if field.endswith("_at"):
        value = _timestamp(row, field)
        return value.astimezone(datetime_timezone.utc).isoformat() if value else None
    return row.get(field, "") or ""


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _canonical_event(event, schema):
    return {field: _canonical_value(event, field) for field in SCHEMAS[schema]}


def history_fingerprint(rows, sku_ids):
    """Canonical within one import format: row order, decimal spelling and offsets do not matter."""
    first = rows[0]
    related = "_shipments" in first
    payload = {"version": 1, "format": "related" if related else "snapshot",
               "order": {field: _canonical_value(first, field) for field in ("source_order_id", "ordered_at", "status", "payment_method", "shipping_total")},
               "lines": [], "payments": []}
    fields = [field for field in SCHEMAS["history"] if field not in {"source_order_id", "sku", "ordered_at", "status", "payment_method", "shipping_total"}]
    if related:
        fields = [field for field in fields if field not in {"collected_amount", "collected_at", "settled_amount", "settled_at"}]
    for row in rows:
        if row["sku"] not in sku_ids:
            raise ImportProblem(f"Unknown SKU: {row['sku']}.")
        line = {field: _canonical_value(row, field) for field in fields}
        line["sku_id"] = str(sku_ids[row["sku"]])
        if related:
            for schema in ("shipments", "returns", "refunds"):
                line[schema] = sorted((_canonical_event(event, schema) for event in row[f"_{schema}"]), key=lambda event: json.dumps(event, sort_keys=True))
            payload["payments"].extend(_canonical_event(event, "payments") for event in row["_payments"])
        payload["lines"].append(line)
    payload["lines"].sort(key=lambda line: line["source_line_id"])
    payload["payments"].sort(key=lambda event: event["source_payment_id"])
    return _digest(payload)


def stock_fingerprint(kind, row, sku_id):
    delta = _integer(row, "quantity" if kind == "opening_stock" else "quantity_delta", minimum=0 if kind == "opening_stock" else None)
    return _digest({"version": 1, "kind": kind, "sku_id": str(sku_id), "delta": delta,
                    "reason": row.get("reason", "") if kind == "adjustments" else ""})


def _assert_exact_repeat(existing_fingerprint, proposed_fingerprint, identity):
    if not existing_fingerprint:
        raise ImportConflict(f"{identity}: existing record has no canonical fingerprint; exactness is unverifiable. Administrator review is required.")
    if existing_fingerprint != proposed_fingerprint:
        raise ImportConflict(f"{identity}: conflicting data for an existing source identifier. Administrator review is required; nothing was replaced.")


def _assert_stock_repeat(movement, fingerprint, sku_id, delta, identity):
    _assert_exact_repeat(movement.import_fingerprint, fingerprint, identity)
    if movement.sku_id != sku_id or movement.on_hand_delta != delta or movement.reserved_delta != 0:
        raise ImportConflict(f"{identity}: stored movement facts do not match the reviewed source identity; administrator reconciliation is required.")


def _group_history(records):
    grouped = defaultdict(list)
    for record in records:
        grouped[record["source_order_id"]].append(record)
    return grouped


def _check_repeat_conflicts(batch, records, sku_ids):
    source = f"csv:{batch.source_name}"
    if batch.kind == "history":
        groups = _group_history(records)
        existing = {order.external_id: order for order in Order.objects.filter(source=source, external_id__in=groups, is_current=True)}
        for external_id, rows in groups.items():
            if external_id in existing:
                _assert_exact_repeat(existing[external_id].import_fingerprint, history_fingerprint(rows, sku_ids), f"Order {external_id}")
    elif batch.kind in {"opening_stock", "adjustments"}:
        references = [f"{source}:{row['source_record_id']}" for row in records]
        existing = {movement.reference: movement for movement in StockMovement.objects.filter(kind=f"import_{batch.kind}", reference__in=references)}
        for row, reference in zip(records, references):
            if reference in existing:
                delta = _integer(row, "quantity" if batch.kind == "opening_stock" else "quantity_delta", minimum=0 if batch.kind == "opening_stock" else None)
                _assert_stock_repeat(existing[reference], stock_fingerprint(batch.kind, row, sku_ids[row["sku"]]), sku_ids[row["sku"]], delta, f"Stock record {row['source_record_id']}")


def _validated_history(batch):
    if batch.kind != "history":
        raise ImportProblem("Reviewed corrections are available only for historical order imports.")
    datasets = read_datasets(batch)
    records = normalize_history(datasets)
    sku_ids = dict(SKU.objects.values_list("code", "id"))
    seen = set()
    for row in records:
        _validate_history_line(row)
        identity = (row["source_order_id"], row["source_line_id"])
        if identity in seen:
            raise ImportProblem("Duplicate source line within the batch.")
        seen.add(identity)
        if row["sku"] not in sku_ids:
            raise ImportProblem(f"Unknown SKU: {row['sku']}.")
    validate_history_consistency(records)
    return _group_history(records), sku_ids


def _proposed_summary(rows):
    value = sum((_decimal(row, "unit_price") * _integer(row, "quantity", minimum=1) - _decimal(row, "discount_total") + _decimal(row, "tax_total") for row in rows), Decimal(0))
    return {"line_count": len(rows), "units": sum(_integer(row, "quantity", minimum=1) for row in rows),
            "grand_total": format((value + _decimal(rows[0], "shipping_total")).quantize(Decimal("0.01")), "f")}


def _existing_summary(order):
    lines = [line.quantity for line in order.lines.all()]
    return {"line_count": len(lines), "units": sum(lines), "grand_total": format(order.grand_total, ".2f")}


def correction_preview(batch):
    groups, sku_ids = _validated_history(batch)
    existing = {order.external_id: order for order in Order.objects.filter(source=f"csv:{batch.source_name}", external_id__in=groups, is_current=True).prefetch_related("lines")}
    orders = []
    expected = {}
    for external_id, rows in sorted(groups.items()):
        fingerprint = history_fingerprint(rows, sku_ids)
        old = existing.get(external_id)
        if old is not None and not old.is_historical:
            raise ImportProblem(f"Order {external_id}: live orders cannot be revised through historical imports.")
        action = "create" if old is None else "skip" if old.import_fingerprint and old.import_fingerprint == fingerprint else "revise"
        if action == "revise":
            expected[external_id] = {"order_id": str(old.id), "fingerprint": old.import_fingerprint}
        orders.append({"external_id": external_id, "action": action, "current_order_id": str(old.id) if old else None,
                       "before_fingerprint": old.import_fingerprint if old else None, "after_fingerprint": fingerprint,
                       "before": _existing_summary(old) if old else None, "after": _proposed_summary(rows)})
    return {"batch_id": str(batch.id), "source_name": batch.source_name, "can_correct": bool(expected) and batch.status not in {"completed", "committing"},
            "orders": orders, "expected_revisions": expected, "conflicts_count": len(expected)}


def prepare_correction(batch, actor, reason, expected_revisions):
    """Validate an administrator's reviewed proposal before durable worker dispatch."""
    if not actor.is_active or not (actor.is_superuser or actor.role == "administrator"):
        raise ImportProblem("Only an active administrator can approve historical corrections.")
    reason = str(reason or "").strip()
    if len(reason) < 10 or len(reason) > 1000:
        raise ImportProblem("A correction reason of 10–1,000 characters is required.")
    preview = correction_preview(batch)
    if not preview["can_correct"]:
        raise ImportProblem("This batch has no conflicting current historical orders to revise.")
    if expected_revisions != preview["expected_revisions"]:
        raise ImportConflict("The reviewed historical revision is stale. Refresh the correction preview before approval.")
    batch.result = {"_correction": {"reason": reason, "reviewer_id": actor.pk, "expected_revisions": expected_revisions,
                                    "after_fingerprints": {row["external_id"]: row["after_fingerprint"] for row in preview["orders"]}}}
    batch.status = "committing"
    batch.progress = 0
    batch.error_rows = 0
    batch.errors = []
    batch.save(update_fields=["result", "status", "progress", "error_rows", "errors"])
    AuditEvent.objects.create(actor=actor, event="historical_correction_requested", entity="import", reference=str(batch.id),
                              details={"reason": reason, "expected_revisions": expected_revisions, "after_fingerprints": batch.result["_correction"]["after_fingerprints"]})
    return preview


def validate_batch(batch_id):
    batch = ImportBatch.objects.get(pk=batch_id)
    if batch.status not in {"queued", "validating"}:
        return batch
    ImportBatch.objects.filter(pk=batch_id).update(status="validating", progress=5)
    try:
        datasets = read_datasets(batch)
        records = normalize_history(datasets) if batch.kind == "history" else datasets[batch.kind]
        errors = []
        seen = set()
        known_skus = dict(SKU.objects.values_list("code", "id"))
        for index, record in enumerate(records):
            try:
                if batch.kind == "catalog":
                    for field in ("product_slug", "product_name", "category", "sku"):
                        _required(record, field)
                    if slugify(record["product_slug"]) != record["product_slug"]:
                        raise ImportProblem("product_slug must already be a URL slug.")
                    _decimal(record, "price")
                    if record.get("cost"):
                        _decimal(record, "cost")
                    identity = record["sku"]
                elif batch.kind in {"opening_stock", "adjustments"}:
                    identity = _required(record, "source_record_id")
                    _integer(record, "quantity" if batch.kind == "opening_stock" else "quantity_delta", minimum=0 if batch.kind == "opening_stock" else None)
                    if batch.kind == "adjustments":
                        _required(record, "reason")
                    if _required(record, "sku") not in known_skus:
                        raise ImportProblem("Unknown SKU; import the catalog first.")
                else:
                    _validate_history_line(record)
                    identity = (record["source_order_id"], record["source_line_id"])
                    if record["sku"] not in known_skus:
                        raise ImportProblem("Unknown SKU; import the catalog first.")
                if identity in seen:
                    raise ImportProblem("Duplicate source identifier within this batch.")
                seen.add(identity)
            except (ImportProblem, InvalidOperation) as exc:
                errors.append({"row": record.get("_row"), "file": record.get("_schema"), "message": str(exc)})
            if index and index % 1000 == 0:
                ImportBatch.objects.filter(pk=batch_id).update(progress=5 + int(90 * index / len(records)))
        if batch.kind == "history" and not errors:
            try:
                validate_history_consistency(records)
            except ImportProblem as exc:
                errors.append({"row": None, "file": "history", "message": str(exc)})
        if batch.kind in {"history", "opening_stock", "adjustments"} and not errors:
            try:
                _check_repeat_conflicts(batch, records, known_skus)
            except ImportConflict as exc:
                errors.append({"row": None, "file": batch.kind, "code": "source_conflict", "message": str(exc)})
        if batch.kind == "catalog" and not errors:
            product_metadata = {}
            existing = dict(SKU.objects.filter(code__in=[row["sku"] for row in records]).values_list("code", "product__slug"))
            for record in records:
                signature = tuple(record.get(field, "") for field in ("product_name", "category", "description", "image_url"))
                slug = record["product_slug"]
                if (slug in product_metadata and product_metadata[slug] != signature) or (record["sku"] in existing and existing[record["sku"]] != slug):
                    errors.append({"row": record["_row"], "file": "catalog", "message": "Inconsistent product metadata or attempt to move an existing SKU to another product."})
                product_metadata[slug] = signature
        batch.total_rows = sum(len(rows) for rows in datasets.values())
        batch.error_rows = len(errors)
        batch.valid_rows = max(0, batch.total_rows - len(errors))
        batch.errors = errors[:100]
        batch.preview = [{key: value for key, value in record.items() if not key.startswith("_")} for record in records[:10]]
        batch.status = "failed" if errors else "ready"
        batch.progress = 100
        batch.save()
    except (ImportProblem, InvalidOperation, IntegrityError) as exc:
        batch.status = "failed"
        batch.errors = [{"row": None, "message": str(exc)[:1000]}]
        batch.progress = 100
        batch.save(update_fields=["status", "errors", "progress"])
    return batch


def _create_history_order(source, external_id, rows, *, fingerprint="", supersedes=None):
    first = rows[0]
    ordered_at = _timestamp(first, "ordered_at")
    number = f"IMP-{hashlib.sha256((source+':'+external_id).encode()).hexdigest()[:24]}"
    if supersedes:
        number += "-" + uuid4().hex[:8]
    order = Order.objects.create(number=number,
                                 source=source, external_id=external_id, is_historical=True, import_fingerprint=fingerprint, supersedes=supersedes,
                                 customer_name="Historical customer", email="historical@example.invalid", phone="", address={},
                                 status=first.get("status") or "delivered", payment_method=first.get("payment_method") or "cod",
                                 created_at=ordered_at, confirmed_at=None,
                                 shipping_total=_decimal(first, "shipping_total"))
    subtotal = Decimal(0)
    discounts = Decimal(0)
    taxes = Decimal(0)
    sku_map = {sku.code: sku for sku in SKU.objects.select_related("product").filter(code__in={row["sku"] for row in rows})}
    shipment_cache = {}
    return_cache = {}
    refund_cache = {}
    refund_totals = defaultdict(Decimal)
    inspected_returns = set()
    for record in rows:
        for event in record.get("_refunds", []):
            refund_totals[event["source_refund_id"]] += _decimal(event, "amount")
        for event in record.get("_returns", []):
            if _integer(event, "accepted_quantity", 0) or _timestamp(event, "inspected_at"):
                inspected_returns.add(event["source_return_id"])
    for record in rows:
        sku = sku_map[record["sku"]]
        line = OrderLine.objects.create(order=order, sku=sku, sku_code=sku.code, product_name=sku.product.name,
                                        variant_name=sku.label, source_line_id=record["source_line_id"],
                                        quantity=_integer(record, "quantity", minimum=1),
                                        cancelled_quantity=_integer(record, "cancelled_quantity", 0),
                                        shipped_quantity=_integer(record, "shipped_quantity", 0),
                                        delivered_quantity=_integer(record, "delivered_quantity", 0),
                                        returned_quantity=_integer(record, "returned_quantity", 0),
                                        unit_price=_decimal(record, "unit_price"), discount_total=_decimal(record, "discount_total"), tax_total=_decimal(record, "tax_total"),
                                        delivered_at=_timestamp(record, "delivered_at"), returned_at=_timestamp(record, "returned_at"))
        subtotal += line.unit_price * line.quantity
        discounts += line.discount_total
        taxes += line.tax_total
        if "_shipments" in record:
            for event in record["_shipments"]:
                completed = _timestamp(event, "completed_at")
                event_id = event["source_shipment_id"]
                shipment = shipment_cache.get(event_id)
                if shipment is None:
                    shipment = Shipment.objects.create(order=order, state=event["state"], tracking_number=event_id, carrier="Historical import",
                                                    dispatched_at=_timestamp(event, "dispatched_at"),
                                                    delivered_at=completed if event["state"] == "delivered" else None, completed_at=completed)
                    shipment_cache[event_id] = shipment
                ShipmentLine.objects.create(shipment=shipment, order_line=line, quantity=_integer(event, "quantity", minimum=1))
        elif line.shipped_quantity:
            shipment = Shipment.objects.create(order=order, state="delivered" if line.delivered_quantity else (order.status if order.status in {"failed", "returned_to_origin"} else "dispatched"),
                                                tracking_number=f"{external_id}-{record['source_line_id']}"[:120], carrier="Historical import", dispatched_at=None,
                                                delivered_at=line.delivered_at, completed_at=line.delivered_at)
            ShipmentLine.objects.create(shipment=shipment, order_line=line, quantity=line.delivered_quantity or line.shipped_quantity)
            if line.delivered_quantity and line.shipped_quantity > line.delivered_quantity:
                pending = Shipment.objects.create(order=order, state="dispatched", tracking_number=f"{external_id}-{record['source_line_id']}-pending"[:120],
                                                  carrier="Historical import", dispatched_at=None)
                ShipmentLine.objects.create(shipment=pending, order_line=line, quantity=line.shipped_quantity-line.delivered_quantity)
        return_events = record.get("_returns")
        if return_events is None and line.returned_quantity:
            return_events = [{"quantity": str(line.returned_quantity), "accepted_quantity": str(line.returned_quantity),
                              "received_at": record.get("returned_at", ""), "inspected_at": record.get("returned_at", ""), "disposition": "quarantine"}]
        for event in return_events or []:
            event_id = event.get("source_return_id") or f"line:{record['source_line_id']}"
            returned = return_cache.get(event_id)
            if returned is None:
                received_at, inspected_at = _timestamp(event, "received_at"), _timestamp(event, "inspected_at")
                accepted = _integer(event, "accepted_quantity", 0)
                returned = ReturnRequest.objects.create(order=order, status="inspected" if inspected_at or accepted or event_id in inspected_returns else "received" if received_at else "requested", reason="Unknown (historical reason not supplied)",
                                                        received_at=received_at, inspected_at=inspected_at)
                return_cache[event_id] = returned
            ReturnLine.objects.create(return_request=returned, order_line=line, quantity=_integer(event, "quantity", minimum=1),
                                      accepted_quantity=_integer(event, "accepted_quantity", 0), restock_quantity=0,
                                      disposition=event.get("disposition") or "quarantine")
        refund_events = record.get("_refunds")
        if refund_events is None and _decimal(record, "refund_amount"):
            refund_events = [{"amount": record["refund_amount"], "tax_amount": record.get("refund_tax_amount", "0"), "shipping_amount": record.get("refund_shipping_amount", "0"),
                              "confirmed_at": record.get("refunded_at", ""), "source_refund_id": record["source_line_id"]}]
        for event in refund_events or []:
            event_id = event["source_refund_id"]
            refund = refund_cache.get(event_id)
            if refund is None:
                refund = Refund.objects.create(order=order, amount=refund_totals.get(event_id) or _decimal(event, "amount"), status="confirmed", reason="Historical refund",
                                                reference=event_id, confirmed_at=_timestamp(event, "confirmed_at"))
                refund_cache[event_id] = refund
            RefundLine.objects.create(refund=refund, order_line=line, amount=_decimal(event, "amount"),
                                      tax_amount=_decimal(event, "tax_amount"), shipping_amount=_decimal(event, "shipping_amount"))
        payment_events = record.get("_payments")
        if payment_events is None and _decimal(record, "collected_amount"):
            payment_events = [{"amount": record["collected_amount"], "collected_at": record.get("collected_at", ""),
                               "settled_amount": record.get("settled_amount", "0"), "settled_at": record.get("settled_at", ""), "method": order.payment_method}]
        for event in payment_events or []:
            event_id = event.get("source_payment_id") or f"line:{record['source_line_id']}"
            payment = Payment.objects.create(order=order, method=event.get("method") or order.payment_method, status="successful",
                                             amount=_decimal(event, "amount"), collected_at=_timestamp(event, "collected_at"),
                                             settled_amount=_decimal(event, "settled_amount"), settled_at=_timestamp(event, "settled_at"),
                                             provider_transaction_id="import:" + hashlib.sha256(f"{source}:{external_id}:{order.id}:{event_id}".encode()).hexdigest())
            if payment.settled_amount:
                PaymentSettlement.objects.create(payment=payment, amount=payment.settled_amount, settled_at=payment.settled_at,
                                                  reference=f"import:{event_id}"[:200], source="import")
    order.subtotal = subtotal
    order.discount_total = discounts
    order.tax_total = taxes
    order.grand_total = subtotal - discounts + taxes + order.shipping_total
    order.delivered_at = max((line.delivered_at for line in order.lines.all() if line.delivered_at), default=None)
    order.save(update_fields=["subtotal", "discount_total", "tax_total", "grand_total", "delivered_at"])
    return order


def commit_batch(batch_id):
    try:
        with transaction.atomic():
            batch = ImportBatch.objects.select_for_update().get(pk=batch_id)
            if batch.status == "completed":
                return batch
            if batch.status not in {"ready", "committing"} or batch.error_rows:
                raise ImportProblem("Only a validated batch without errors can commit.")
            batch.status = "committing"
            batch.progress = 5
            batch.save(update_fields=["status", "progress"])
            datasets = read_datasets(batch)
            records = normalize_history(datasets) if batch.kind == "history" else datasets[batch.kind]
            counts = {"created": 0, "updated": 0, "skipped": 0}
            correction = batch.result.get("_correction") if isinstance(batch.result, dict) else None
            source = f"csv:{batch.source_name}"
            # Serialize repeated source batches, including different worker processes.
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", [source])
            if batch.kind == "history":
                grouped, sku_ids = _validated_history(batch)
                existing = {order.external_id: order for order in Order.objects.select_for_update().filter(source=source, external_id__in=grouped, is_current=True)}
                fingerprints = {external_id: history_fingerprint(rows, sku_ids) for external_id, rows in grouped.items()}
                conflicts = {external_id: old for external_id, old in existing.items() if not old.import_fingerprint or old.import_fingerprint != fingerprints[external_id]}
                reviewer = None
                if correction:
                    from django.contrib.auth import get_user_model
                    reviewer = get_user_model().objects.filter(pk=correction.get("reviewer_id"), is_active=True).first()
                    if reviewer is None or not (reviewer.is_superuser or reviewer.role == "administrator"):
                        raise ImportProblem("The approving administrator no longer has correction access.")
                    expected = {external_id: {"order_id": str(old.id), "fingerprint": old.import_fingerprint} for external_id, old in conflicts.items()}
                    if expected != correction.get("expected_revisions") or fingerprints != correction.get("after_fingerprints"):
                        raise ImportConflict("The reviewed historical revision or proposal is stale. Refresh the correction preview.")
                    if any(not old.is_historical for old in conflicts.values()):
                        raise ImportProblem("Live orders cannot be revised through historical imports.")
                    counts["revised"] = 0
                else:
                    for external_id, old in existing.items():
                        _assert_exact_repeat(old.import_fingerprint, fingerprints[external_id], f"Order {external_id}")
                for external_id, rows in sorted(grouped.items()):
                    old = existing.get(external_id)
                    if old is not None and external_id not in conflicts:
                        counts["skipped"] += len(rows)
                        continue
                    if old is not None:
                        old.is_current = False
                        old.save(update_fields=["is_current"])
                    created = _create_history_order(source, external_id, rows, fingerprint=fingerprints[external_id], supersedes=old)
                    counts["created"] += len(rows)
                    if old is not None:
                        counts["revised"] += 1
                        AuditEvent.objects.create(actor=reviewer, event="historical_order_corrected", entity="order", reference=str(created.id),
                                                  details={"batch_id": str(batch.id), "reason": correction["reason"], "external_id": external_id,
                                                           "before_order_id": str(old.id), "after_order_id": str(created.id),
                                                           "before_fingerprint": old.import_fingerprint, "after_fingerprint": fingerprints[external_id]})
            else:
                for record in records:
                    if batch.kind == "catalog":
                        if SKU.objects.filter(code=record["sku"]).exclude(product__slug=record["product_slug"]).exists():
                            raise ImportProblem("An existing SKU cannot move to another product.")
                        product, _ = Product.objects.update_or_create(slug=record["product_slug"], defaults={"name": record["product_name"], "category": record["category"],
                                                                                                       "description": record.get("description", ""), "image_url": record.get("image_url", "")})
                        _, created = SKU.objects.update_or_create(code=record["sku"], defaults={"product": product, "label": record.get("variant_name", ""),
                                                                                               "price": _decimal(record, "price"), "cost": _decimal(record, "cost") if record.get("cost") else None})
                        counts["created" if created else "updated"] += 1
                    else:
                        sku = SKU.objects.select_for_update().get(code=record["sku"])
                        reference = f"{source}:{record['source_record_id']}"
                        fingerprint = stock_fingerprint(batch.kind, record, sku.id)
                        prior = StockMovement.objects.filter(reference=reference, kind=f"import_{batch.kind}").first()
                        if prior:
                            delta = _integer(record, "quantity" if batch.kind == "opening_stock" else "quantity_delta", minimum=0 if batch.kind == "opening_stock" else None)
                            _assert_stock_repeat(prior, fingerprint, sku.id, delta, f"Stock record {record['source_record_id']}")
                            counts["skipped"] += 1
                            continue
                        if batch.kind == "opening_stock":
                            if sku.on_hand or sku.reserved or sku.movements.exists() or sku.order_lines.filter(order__is_historical=False).exists():
                                raise ImportProblem(f"{sku.code}: opening stock requires a new SKU with no stock history.")
                            delta = _integer(record, "quantity")
                        else:
                            delta = _integer(record, "quantity_delta", minimum=None)
                        if sku.on_hand + delta < sku.reserved:
                            raise ImportProblem(f"{sku.code}: adjustment would violate stock reservations.")
                        sku.on_hand += delta
                        sku.save(update_fields=["on_hand"])
                        StockMovement.objects.create(sku=sku, on_hand_delta=delta, kind=f"import_{batch.kind}", reference=reference, actor=batch.created_by, import_fingerprint=fingerprint)
                        counts["created"] += 1
            batch.status = "completed"
            batch.progress = 100
            batch.committed_at = timezone.now()
            batch.result = counts
            if correction:
                batch.result["correction_reason"] = correction["reason"]
                batch.result["reviewer_id"] = correction["reviewer_id"]
            batch.save(update_fields=["status", "progress", "committed_at", "result"])
            AuditEvent.objects.create(actor=batch.created_by, event="import_committed", entity="import", reference=str(batch.id), details=counts)
            return batch
    except (ImportProblem, InvalidOperation, IntegrityError) as exc:
        ImportBatch.objects.filter(pk=batch_id).exclude(status="completed").update(status="failed", progress=100,
                                                                                   errors=[{"row": None, "message": str(exc)[:1000]}])
        return ImportBatch.objects.get(pk=batch_id)
