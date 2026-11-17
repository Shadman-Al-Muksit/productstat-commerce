# Reporting and import API contract

All endpoints are below `/api/v1/`. Analytics permits the administrator, operator and analyst company roles; imports permits administrators and operators. A Django `is_staff` flag does not grant access on its own. Session authentication and CSRF apply. Monetary values are BDT decimal strings. Dates use Asia/Dhaka; `start` and `end` are inclusive calendar dates. Defaults cover the last 30 days including today. `product_ids` is an optional comma-separated list of at most 20 product UUIDs.

## Analytics

`GET analytics/?start=2026-01-01&end=2026-01-31&product_ids=<uuid>`

```json
{
  "filters": {"start":"2026-01-01","end":"2026-01-31","timezone":"Asia/Dhaka","product_ids":[],"currency":"BDT"},
  "summary": {"orders":100,"ordered_units":300,"ordered_value":"150000.00","delivered_units":250,"delivered_value":"125000.00","returned_units":10,"refunded_amount":"5000.00","net_delivered_value":"120000.00"},
  "cohort": {"delivered_units":250,"returned_units":12,"return_rate":4.8,"open_window_units":20,"preliminary":true,"as_of":"2026-02-01T12:00:00+06:00","basis":"Delivered units in the selected interval, accepted returns observed to date; split deliveries allocate accepted returns FIFO."},
  "cash": {"scope":"company","product_filter_applied":false,"collected_amount":"130000.00","cod_collected_amount":"100000.00","online_collected_amount":"30000.00","settled_amount":"90000.00","exception_collected_amount":"0.00","sandbox_collected_amount":"0.00","basis":"Recorded cash event dates; includes shipping/tax, always company-wide. Sandbox/demo records are not real funds."},
  "delivery": {"delivered_shipments":85,"failed_shipments":8,"returned_to_origin_shipments":7,"terminal_shipments":100,"success_rate":85.0,"basis":"Delivered / (delivered + failed + returned to origin), terminal event date. Pending shipments excluded."},
  "comparison": {"start":"2025-12-01","end":"2025-12-31","summary":{},"change_percent":{}},
  "trend": [{"date":"2026-01-01","ordered_value":"5000.00","delivered_value":"4500.00","refunded_amount":"0.00","ordered_units":10,"delivered_units":9,"returned_units":0}],
  "products": [{"id":"uuid","name":"Everyday Tote","category":"Bags","image_url":"/products/tote.svg","ordered_units":30,"delivered_units":25,"returned_units":1,"delivered_value":"12500.00","refunded_amount":"500.00","net_delivered_value":"12000.00"}],
  "meta": {"generated_at":"2026-02-01T12:00:00+06:00","basis":"Activity uses each event date; return cohort follows deliveries in the selected period, observed to date.","customer_data":"Excluded","money_basis":"Merchandise after discounts; excludes shipping and tax. Not accounting profit."}
}
```

Activity returns and cohort returns intentionally differ: January delivery-cohort returns can be accepted in February. `preliminary` flags deliveries still inside the configured return window. Zero denominators yield `null` rates. The equal-length previous interval supplies comparison values; a zero prior value yields `null` percent change. Cash totals remain company-wide when products are selected, because actual payments include order-level shipping and tax. Verified exception receipts are included and separately identified as refund obligations. Refund merchandise amounts subtract immutable tax/shipping allocations from cash refund-line amounts.

`cash.settled_amount` sums individual settlement events in the interval; it never sums a payment's cumulative balance on its latest timestamp. Legacy aggregate settlement events retain explicitly limited historical provenance, described in `METRICS.md`.

HTTP overviews use a shared cache for up to 30 seconds, invalidated by committed business audit/import revisions. `meta.generated_at` and cohort `as_of` remain the actual calculation times on cache hits. `X-Analytics-Cache` indicates `HIT`, `MISS`, `WAIT-HIT`, `BYPASS`, or `LOCK-TIMEOUT`; browsers/proxies receive `Cache-Control: private, no-store`. Redis errors fall back to the database. Drill-down/export are uncached. Direct analytical function calls also remain uncached for reconciliation and fixtures.

`GET analytics/drilldown/?metric=delivered_units&start=...&end=...&page=1&page_size=50`

Metrics: `orders`, `ordered_units`, `delivered_units`, `returned_units`, `refunds`. Rows exclude customer names, emails, phones and addresses.

```json
{"metric":"delivered_units","count":1,"page":1,"page_size":50,"results":[{"id":"uuid","order_number":"PS-000001","product_id":"uuid","product_name":"Everyday Tote","sku":"BAG-0001","quantity":2,"value":"1000.00","event_at":"2026-01-04T10:00:00+06:00","status":"delivered","source":"demo"}]}
```

`GET analytics/export/?metric=delivered_units&start=...&end=...` downloads exactly the same filtered, redacted rows as the drill-down, without pagination.

## Imports

`GET imports/` returns `{"results":[<batch>]}`.

`POST imports/`: multipart fields `kind` (`catalog`, `opening_stock`, `adjustments`, `history`), `source_name` (stable source identity), and `file` or repeated `files` (UTF-8 CSV, at most 10 MB / 25,000 total data rows). Returns HTTP 202 with the new batch. Validation runs asynchronously; importing cannot change stock or historical order data until commit. A normalized history batch requires `orders.csv` and `lines.csv`, with optional `shipments.csv`, `returns.csv`, `refunds.csv`, `payments.csv`. Shared event identifiers create one shipment/return/refund with multiple lines, not duplicate parent events. A single denormalized history CSV is also supported.

`GET imports/<id>/` returns:

```json
{"id":"uuid","kind":"history","status":"ready","filename":"history.csv","source_name":"legacy-2026","progress":100,"total_rows":3,"valid_rows":3,"error_rows":0,"errors":[],"preview":[{}],"result":{},"created_at":"...","committed_at":null}
```

Status sequence: `queued` → `validating` → `ready` → `committing` → `completed`; invalid data or exhausted worker retries use `failed`. Error entries have `row`, optional `file`, and `message`. A batch with errors cannot commit. `result` records created, updated and skipped line/record counts after commit. Repeat source order identifiers are skipped, never counted as new sales. History is immutable; repeated source orders do not merge changes. Validation reports progress in chunks; atomic commit progress is visible principally at its boundaries.

The upload/commit event is stored transactionally in the database before broker dispatch. A broker outage leaves the event pending. Celery beat retries pending work; transient failures back off from 30 seconds up to 15 minutes, with eight attempts. A worker's five-minute claim lease can be recovered after a crash. Import commits lock the batch/source and are replay-safe. External email has at-least-once delivery semantics and is suppressed in public demo mode.

`POST imports/<id>/commit/` returns HTTP 202. Repeating commit for a completed batch returns that batch without reapplying changes.

`GET imports/templates/?kind=history` returns a CSV template for the selected kind. The exact columns and rules are documented in `IMPORTS.md`.

Demo product image filenames: `tote.svg`, `headphones.svg`, `lamp.svg`, `bottle.svg`, `watch.svg`, `chair.svg` in `/products/`.
