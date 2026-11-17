# Architecture and data ownership

```mermaid
flowchart LR
  Customer[Customer storefront] --> Proxy[Same-origin HTTPS proxy]
  Staff[Staff and analyst workspace] --> Proxy
  Proxy --> Next[Next.js interface]
  Proxy --> API[Django REST API]
  API --> PG[(PostgreSQL)]
  API --> Outbox[Transactional outbox]
  Outbox --> Worker[Celery worker]
  Beat[Periodic dispatcher] --> Worker
  Worker --> PG
  Worker --> Mail[Configured notification transport]
  API --> Gateway[SSLCOMMERZ sandbox validation]
  PG --> Reports[Reporting queries]
  Reports --> API
```

Django is the authority for money, stock, permissions and transitions. Next.js does not duplicate checkout or reporting rules. Cookies use the shared origin, and unsafe guest requests receive the same CSRF protection as authenticated requests.

## Main relationships

```mermaid
erDiagram
  PRODUCT ||--o{ SKU : offers
  SKU ||--o{ ORDER_LINE : identifies
  ORDER ||--|{ ORDER_LINE : contains
  ORDER ||--o{ PAYMENT : records
  PAYMENT ||--o{ PAYMENT_SETTLEMENT : settles_in_increments
  ORDER o|--o{ ORDER : supersedes_historical_revision
  ORDER ||--o{ SHIPMENT : fulfils
  SHIPMENT ||--|{ SHIPMENT_LINE : contains
  ORDER_LINE ||--o{ SHIPMENT_LINE : allocates
  ORDER ||--o{ RETURN_REQUEST : receives
  RETURN_REQUEST ||--|{ RETURN_LINE : contains
  ORDER_LINE ||--o{ RETURN_LINE : references
  ORDER ||--o{ REFUND : owes
  REFUND ||--|{ REFUND_LINE : allocates
  SKU ||--o{ STOCK_MOVEMENT : audits
```

Product and SKU changes do not rewrite historical order snapshots. `on_hand − reserved` is available stock. Checkout locks inventory; dispatch consumes reservations; cancellation releases them; inspected returns create separate stock movements. A refund is a money record, independent of physical receipt.

Live checkout supports one shipment. Historical migration can retain external event identities from related CSV files. Historical observations feed supported reports but never replay live operations.

Historical source identities permit one current revision. An administrator-approved correction preserves the previous order and its immutable payment, settlement and event records, then creates a linked replacement. Reporting uses current revisions; audit records retain the reviewer, reason and previous/new identifiers. Unknown historical dates remain NULL, with coverage reported separately from dated metrics. This does not change live inventory or replay customer operations.

## Decisions

- Modular monolith: transactional boundaries stay in one database. Celery runs the same backend codebase.
- Decimal money with BDT currency; UTC storage and Asia/Dhaka business dates.
- Operational reporting stays in PostgreSQL. A separate warehouse is unnecessary for the selected workload.
- Stock movements and audit events explain changes; imported files remain private.
- Delivery cohorts prevent unrelated monthly sales and returns from being combined into a misleading rate.
- Synthetic demonstration records live in their own deployment/database. Financial test activity cannot enter a real company fulfilment workflow.
- Versioned REST APIs and generated TypeScript definitions make wire changes reviewable.
