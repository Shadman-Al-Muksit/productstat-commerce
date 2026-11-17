# Import contract

Imports require an administrator or operator. Analyst access is read-only. Files remain in private media storage and are never exposed as public product media.

Upload UTF-8 CSV using multipart `file` or repeated `files` fields, plus `kind` and a stable `source_name`. A batch accepts at most **10 MB and 25,000 data rows across all files**. Duplicate headers, unknown columns, inconsistent row widths and unknown SKUs fail validation. Download exact headers from `/api/v1/imports/templates/?kind=<schema>`.

The sequence is upload → asynchronous validation → preview/errors → explicit commit → asynchronous atomic write. A durable database outbox records work before Celery dispatch; if Redis is unavailable, pending work survives for the periodic dispatcher. Transient failures retry after 30 seconds with exponential backoff capped at 15 minutes, up to eight attempts. A dead worker's five-minute lease expires for recovery. Inspect batch status and result counters. A failed validation never changes business records. A failed commit rolls back the entire batch. Atomic commits cannot expose per-row committed progress; the progress indicator primarily advances at validation chunks and transaction boundaries.

## Catalogue and stock

| Kind | Columns |
|---|---|
| `catalog` | `product_slug,product_name,category,description,image_url,sku,variant_name,price,cost` |
| `opening_stock` | `source_record_id,sku,quantity` |
| `adjustments` | `source_record_id,sku,quantity_delta,reason` |

Catalogue imports upsert products by slug and variants by unique SKU. They do not change stock and cannot move an existing SKU to a different product. Rows sharing a product slug must agree on product metadata. An opening-stock row is permitted only when that SKU has no stock/reservation/movement history or live order history; imported historical orders can precede a separately reconciled initial stock import. Adjustments add/subtract quantities and cannot leave on-hand stock below reserved stock. Stock movement identity is source name plus source record ID; repeating it is skipped. Different corrections require different record IDs.

## Historical order batches

Use `kind=history`. Supply either one denormalized CSV or a related-file batch. Historical imports create order snapshots and events directly: **they do not reserve stock, dispatch goods, call payment providers, restock returned units, send customer messages or alter live inventory**. Import current stock separately.

History identity is `source_name + source_order_id`; line identity adds `source_line_id`. Reimporting an existing source order skips it entirely and reports the skip count. It does not amend the old order. Use a new source only for a genuinely different dataset, never to bypass duplicate detection. This release does not provide historical correction/merge tooling.

### One denormalized file

Template kind `history` has these columns:

```text
source_order_id,source_line_id,sku,ordered_at,status,payment_method,shipping_total,quantity,unit_price,discount_total,tax_total,cancelled_quantity,shipped_quantity,delivered_quantity,delivered_at,returned_quantity,returned_at,refund_amount,refund_tax_amount,refund_shipping_amount,refunded_at,collected_amount,collected_at,settled_amount,settled_at
```

Each row is one order line. Collection, settlement, line-tax and refund amounts are **line-specific amounts**, not repeated full order totals. `shipping_total` is the one order-wide charge and must agree across lines. Order timestamps, status and payment method must also agree. This format is convenient for simple historical snapshots: dispatch dates are unavailable and recorded as the order date; use related files for exact dispatch/terminal events, split deliveries, multiple returns or payment events. Optional tax columns default to zero and must be supplied when the source charged/refunded tax. Merchandise reporting subtracts refund tax/shipping allocations from the cash refund amount.

### Related CSV files in one batch

Files must have these exact names. `orders.csv` and `lines.csv` are required; the rest are optional when their events did not occur.

| Filename / template kind | Columns |
|---|---|
| `orders.csv` / `orders` | `source_order_id,ordered_at,status,payment_method,shipping_total` |
| `lines.csv` / `lines` | `source_order_id,source_line_id,sku,quantity,unit_price,discount_total,tax_total,cancelled_quantity` |
| `shipments.csv` / `shipments` | `source_order_id,source_line_id,source_shipment_id,state,quantity,dispatched_at,completed_at` |
| `returns.csv` / `returns` | `source_order_id,source_line_id,source_return_id,quantity,accepted_quantity,received_at,inspected_at,disposition` |
| `refunds.csv` / `refunds` | `source_order_id,source_line_id,source_refund_id,amount,tax_amount,shipping_amount,confirmed_at` |
| `payments.csv` / `payments` | `source_order_id,source_payment_id,method,amount,collected_at,settled_amount,settled_at` |

Money must be finite, nonnegative, and have at most two decimal places. Positive quantities/amounts require their event timestamps. Timestamps must include timezone offsets and cannot be in the future. Event dates cannot precede order creation; settlement cannot precede collection. Quantities must satisfy cancelled + shipped ≤ ordered, delivered ≤ shipped and accepted returns ≤ delivered. Discounts cannot exceed merchandise value, settlements cannot exceed collections, and recorded refunds cannot exceed collected money or line value.

Order states: `pending_payment,confirmed,preparing,dispatched,delivered,failed,returned_to_origin,cancelled`. Shipment states: `dispatched,delivered,failed,returned_to_origin`. Payment methods: `cod,sslcommerz`. Return dispositions: `restock,quarantine,dispose`; imported historical disposition is informational and never changes current stock.

Within one source order, shared `source_shipment_id`, `source_return_id` and `source_refund_id` values group multiple contributing lines into one parent event. Their parent timestamps/state must agree. Duplicate source event/line pairs and duplicate `source_payment_id` values fail before commit. A return cannot precede sufficient delivered quantities, and a refund cannot precede sufficient recorded collections. Repeated source batches serialize in PostgreSQL and cannot double-write order or stock effects. Retain original exports for reconciliation.

Every positive imported `settled_amount` creates one immutable settlement event with provenance `import`, tied to the payment and its stable record identity. It is a snapshot at the supplied `settled_at`, not a reconstruction of earlier partial bank/courier transfers. Do not repeat a cumulative amount across payment records; this schema requires one unique payment record and rejects duplicate `source_payment_id` values. Source histories needing finer historical settlement periods must retain the original transfer records for reconciliation; the importer does not invent their dates.
