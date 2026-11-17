# Metric dictionary

All reports use Asia/Dhaka calendar boundaries. `start` and `end` are inclusive dates; the database interval is start midnight through midnight after end. Product filters select matching order lines; distinct orders are counted once. Monetary values use decimal arithmetic and BDT. SKU prices and discounts are order snapshots, so editing today's catalogue price does not rewrite history.

| Metric | Definition / event date |
|---|---|
| Orders | Distinct orders with selected lines, placed during the interval. Includes subsequently cancelled orders. |
| Ordered units / value | Original line quantity / merchandise value after line discounts, on order creation date. Includes cancelled units; this measures demand, not completed sales. |
| Delivered units / value | Quantities on delivered shipment events / allocated net line price × quantity, on actual delivery date. Split shipments remain separate events. |
| Returned units | Accepted quantities from inspected returns, on inspection date. Requested or rejected returns are excluded. |
| Refunded amount | Confirmed refund-line cash amounts minus their tax/shipping allocations, on confirmation date. Pending refunds are excluded. Each refund has exact line allocations. |
| Net delivered value | Delivered merchandise value minus confirmed merchandise refund allocations occurring in the interval. Refunds can concern older deliveries; a negative interval is valid. |
| Delivery success | Delivered shipments / (delivered + failed + returned-to-origin shipments), using each shipment's terminal date. Pending shipments are excluded. A shipment containing multiple selected products is counted once. |
| Collections | Verified successful and exception payment receipts, on collection date. COD and online collection are separate. Includes shipping/tax. Exception receipts are separately exposed as refund obligations; sandbox receipts are separately identified. |
| Settlement | Recorded settled payment amounts, on settlement date. Collection and settlement are different events. |

Collections and settlements are **company-wide**, even when merchandise reports filter products. An order-level cash payment includes delivery charges and cannot honestly be assigned to one SKU without a separately documented allocation. The API explicitly returns `cash.scope = company` and `product_filter_applied = false`.

## Return rate: delivery cohort

The denominator is units delivered during the selected interval. The numerator is accepted returned units attributable to those deliveries, observed through the report's `as_of` timestamp. This is different from dividing return activity in a month by delivery activity in that month: returns often happen later.

When the same order line has split deliveries and the return does not identify a shipment, accepted returns allocate to eligible earlier deliveries first (FIFO). A return cannot allocate to a delivery after the return event. The reference test includes a January/February split delivery and a February return attributed to January's delivery cohort.

`open_window_units` counts cohort deliveries still within the configured return window; `preliminary` is true while any remain. This is a maturity indicator, not a guarantee that no late exception return will be accepted. A zero denominator produces `null`, not a misleading 0% rate.

## Comparison, drill-down and limitations

The previous comparison interval contains the same number of calendar days immediately before the selected interval. Percent change is `null` when the previous value is zero. Trend buckets contain every day, including zero-activity days.

Drill-down and CSV export use the same selection function. They contain order references and merchandise facts, and exclude customer names, email, phone and addresses. For `metric=orders`, rows represent contributing order lines; the headline order total is the distinct order count, not the row count. CSV values are protected against spreadsheet formula injection.

Merchandise values exclude shipping and tax. They are operational sales measures, **not accounting revenue or profit**. No profit metric is published because warehouse, courier, marketing, tax and other costs are not comprehensively modelled. Sandbox/demo collections are synthetic and do not represent money received.

New live operations, normalized CSV imports and the full seed create shipment/return event records. Snapshot-only legacy records fall back to line delivery/return timestamps; they cannot reconstruct missing split-event history. Reports should not be claimed as complete for an external source that omitted those events.

Dashboard SQL groups the same event stream into headline, day and product totals in PostgreSQL without loading the full transactional dataset into the web process. HTTP overviews share a Redis cache for up to 30 seconds, keyed by canonical filters and committed audit/import revisions. Every supported business write appends an audit event inside its database transaction; an append-count revision also detects an older transaction committing after a newer timestamp. A committed write therefore causes the next overview to calculate fresh totals. Direct SQL/ORM maintenance must append its audit event too; fresh demo seeding does so automatically.

Cached responses retain the original visible `meta.generated_at` and cohort `as_of`; they do not claim to have been calculated again. A bounded Redis lock reduces duplicate work for simultaneous readers. Redis failures fall back to fresh database calculations, and browsers/proxies receive `private, no-store` so they cannot bypass revision checks. Drill-down, CSV export and the analytical function itself remain uncached. The hand-calculated reference and cache tests verify cross-month split deliveries, subsequent returns, exact discounts, tax/shipping refund exclusion, CSV reconciliation, and immediate refresh after checkout, return, refund and historical import commits.
