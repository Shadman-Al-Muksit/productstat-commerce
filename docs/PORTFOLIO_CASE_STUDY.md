# ProductStat Commerce: connecting commerce operations to product decisions

## Problem

A product can receive many orders while losing value through failed delivery, accepted returns or unsettled collections. A sales total alone cannot explain those outcomes. ProductStat connects the customer purchase journey to staff operations and record-level analytics for one Bangladesh retailer.

## What the implementation demonstrates

The storefront supports variants, cart, guest/account checkout and private tracking. Staff manage reservations, preparation, dispatch, delivery outcomes, COD collection/settlement and returns. Product intelligence uses the same transaction records, not a second set of invented chart values.

The PostgreSQL demonstration contains 25,000 synthetic historical orders and 75,000 order lines across 2,000 SKUs. Verification adds a small number of clearly synthetic operational records. Product names, demand patterns, outcomes and money values are generated examples; they are not observations from a real company.

## Worked investigation

1. Compare products over the same reporting interval and distinguish ordered units from delivered merchandise.
2. Open the delivery analysis to inspect finalized delivery failures and return-to-origin outcomes. In-transit shipments remain separate.
3. Review accepted returns against the corresponding delivery cohort, with an observation cutoff and preliminary/outstanding-case indicators.
4. Open a contributing record to identify the SKU, quantity, event date, saved merchandise amount and source.
5. Compare collected COD, courier settlement and confirmed refunds separately from merchandise value. Export the same redacted event rows for further analysis.

A high return rate suggests a product or fulfilment issue worth investigating; it does not prove its cause. Immature cohorts and small denominators require care. The demonstration cannot support claims about a real company's customers or commercial performance.

## Engineering decisions

- Use one transactional backend and database to keep stock and money transitions coherent.
- Reserve stock under database locks and bind checkout retries to their original request/session.
- Preserve order-line prices, discounts and tax snapshots instead of joining today's catalogue prices into historical calculations.
- Group shared imported shipment/return/refund identities before counting outcomes.
- Keep queued work in a durable database outbox, with bounded retries and dead-worker recovery.
- Define metrics once and reuse them for the dashboard, drill-down and CSV exports.
- Use an explicit private/public-media boundary and backend role permissions.

## Evidence and limitations

The test suite includes real PostgreSQL checkout contention, authorization, partial-return/refund accounting and exact report fixtures. Browser tests follow a purchase through COD delivery, settlement, a partial return and refund, then verify the product measures. Real-worker tests demonstrate an identical import being skipped and a queued batch completing after worker restart. Encrypted backup restoration verifies database totals and private-file checksums.

Measured results, benchmark conditions and unresolved external release prerequisites are maintained in [VALIDATION.md](VALIDATION.md). Hosted deployment and actual merchant gateway transactions require their own evidence.
