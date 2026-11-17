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

Catalogue imports upsert products by slug and variants by unique SKU. They do not change stock and cannot move an existing SKU to a different product. Rows sharing a product slug must agree on product metadata. An opening-stock row is permitted only when that SKU has no stock/reservation/movement history or live order history; imported historical orders can precede a separately reconciled initial stock import. Adjustments add/subtract quantities and cannot leave on-hand stock below reserved stock. Stock movement identity is source name plus source record ID within its import kind. An exact repeat is skipped only when the canonical SKU identity, signed quantity and reason agree. Changing an existing identifier's quantity, SKU or reason fails clearly without changing stock. Legacy movements without a fingerprint are explicitly unverifiable and cannot be silently replayed. A real stock correction uses a new audited adjustment identity and reason, preserving the original movement.

## Historical order batches

Use `kind=history`. Supply either one denormalized CSV or a related-file batch. Historical imports create order snapshots and events directly: **they do not reserve stock, dispatch goods, call payment providers, restock returned units, send customer messages or alter live inventory**. Import current stock separately.

History identity is `source_name + source_order_id`; line identity adds `source_line_id`. An exact repeat is skipped only when a stored canonical fingerprint matches the complete proposed order, its lines and its events. Fingerprints normalize decimal spelling and timezone offsets and ignore CSV file/line ordering; they use stable SKU UUIDs. Snapshot and related-file formats retain distinct representations because their event identities differ. A changed or unverifiable existing source identity fails normal validation/commit and requires administrator review. Use a new source only for a genuinely different dataset, never to bypass conflicts.

### One denormalized file

Template kind `history` has these columns:

```text
source_order_id,source_line_id,sku,ordered_at,status,payment_method,shipping_total,quantity,unit_price,discount_total,tax_total,cancelled_quantity,shipped_quantity,delivered_quantity,delivered_at,returned_quantity,returned_at,refund_amount,refund_tax_amount,refund_shipping_amount,refunded_at,collected_amount,collected_at,settled_amount,settled_at
```

Each row is one order line. Collection, settlement, line-tax and refund amounts are **line-specific amounts**, not repeated full order totals. `shipping_total` is the one order-wide charge and must agree across lines. Order timestamps, status and payment method must also agree. This format is convenient for simple historical snapshots: dispatch dates are unavailable and remain NULL; they are never replaced with the order date. Use related files for observed dispatch/terminal events, split deliveries, multiple returns or payment events. Optional tax columns default to zero and must be supplied when the source charged/refunded tax. Merchandise reporting subtracts refund tax/shipping allocations from the cash refund amount.

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

Money must be finite, nonnegative, and have at most two decimal places. Historical timestamps, including `ordered_at`, may be blank and remain NULL even when an event quantity or amount is positive. A supplied timestamp must include its timezone offset and cannot be in the future. Chronology is checked when both relevant dates are known: an event cannot precede a known order date, and settlement cannot precede a known collection date. Unknown dates cannot prove chronology; quantity and monetary bounds remain mandatory. Quantities must satisfy cancelled + shipped ≤ ordered, delivered ≤ shipped and accepted returns ≤ delivered. Discounts cannot exceed merchandise value, settlements cannot exceed collections, and recorded refunds cannot exceed collected money or line value.

The import batch's creation/commit timestamps retain ingestion provenance. Payment and return-record `created_at` timestamps also describe ingestion; they are not substituted for missing observed collection/return timestamps. Reports exclude undated events from calendar totals and expose reporting coverage separately, without inventing dates.

Order states: `pending_payment,confirmed,preparing,dispatched,delivered,failed,returned_to_origin,cancelled`. Shipment states: `dispatched,delivered,failed,returned_to_origin`. Payment methods: `cod,sslcommerz`. Return dispositions: `restock,quarantine,dispose`; imported historical disposition is informational and never changes current stock.

Within one source order, shared `source_shipment_id`, `source_return_id` and `source_refund_id` values group multiple contributing lines into one parent event. Their parent timestamps/state must agree. Duplicate source event/line pairs and duplicate `source_payment_id` values fail before commit. Fully dated event histories also verify that accepted returns and refunds do not precede sufficient deliveries/collections. Repeated source batches serialize in PostgreSQL and recheck their fingerprints at commit, preventing double writes or changes between preview and commit. Retain original exports for reconciliation.

Every positive imported `settled_amount` creates one immutable settlement event with provenance `import`, tied to the payment and its stable record identity. It is a snapshot at the supplied `settled_at`, not a reconstruction of earlier partial bank/courier transfers. Do not repeat a cumulative amount across payment records; this schema requires one unique payment record and rejects duplicate `source_payment_id` values. Source histories needing finer historical settlement periods must retain the original transfer records for reconciliation; the importer does not invent their dates.

## Reviewed administrator historical corrections

Historical corrections preserve every prior order, payment, refund, settlement and fulfilment record. The administrator approves a new revision; the previous historical order becomes `is_current=false`, and the new order links to it through `supersedes`. Only one revision of a source order is current. Reports use current revisions, so the corrected order replaces the old reporting contribution without double counting. This is not a destructive history replacement and cannot change live orders or inventory.

1. Upload the corrected CSV under its original `source_name` and stable order IDs. Normal validation reports conflicting identities.
2. An administrator calls `GET /api/v1/imports/<batch_id>/correction-preview/`. The response contains `orders` with action `create`, `skip` or `revise`, current order UUID, before/after fingerprints and line-count/unit/grand-total summaries. `expected_revisions` binds each proposed revision to the reviewed current UUID and fingerprint. Legacy empty fingerprints remain explicit and still require this review.
3. Approve with `POST /api/v1/imports/<batch_id>/correct/` and the exact preview map:

```json
{"reason":"Reconciled corrected supplier export against the retained source records","expected_revisions":{"ORDER-123":{"order_id":"current-order-uuid","fingerprint":"current-fingerprint-or-empty-for-legacy"}}}
```

The reason must contain 10–1,000 characters. Approval is available only after validation finishes (`ready` or `failed`); queued/actively validating batches cannot be approved. Validator status/progress updates are conditional, so a delayed validation job cannot overwrite an approved or completed correction. The endpoint returns HTTP202 with the normal batch response and schedules the existing durable import worker. The worker locks the source/current records and rechecks the prior UUID, fingerprint, approved proposal and administrator access. A stale review fails without changing any order. The completed batch reports `revised` orders alongside normal created/skipped line counts. Successful revisions append audit records containing the reviewer, reason, batch identity and before/after order IDs/fingerprints in the same database transaction.

Operators, analysts and customers cannot preview or approve corrections. Business-invalid CSVs cannot be repaired by approval. Corrections do not call gateways or send historical customer notifications, and no old financial event is edited or deleted. The stored prior revisions remain available for audit; changing a source name to bypass review would still create duplicate business facts and must never be used as a correction workflow.
