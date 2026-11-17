# ProductStat Commerce — stopped checkpoint

Saved: 16 November 2026, approximately 18:56 Asia/Dhaka.

## Stop instruction

The user said **"mark a checkpoint to stop"**. Implementation stopped immediately. All three implementation agents were interrupted, reported their state, and stopped. Do not continue automatically or schedule work. Resume only after a new user instruction.

**This is an incomplete implementation, not a working release and not production ready.** Preserve the files and existing database. The frontend is not build-ready. Latest schema changes have not been reverified.

## Agreed product and implementation

Single-company Bangladesh physical-goods e-commerce platform with customer storefront, company administration and product analytics. BDT / Asia-Dhaka, one warehouse, guest checkout and optional customer accounts, COD plus SSLCOMMERZ hosted sandbox, manual courier updates, partial cancellations and returns, separate order/payment/shipment/return/refund states, secure guest tracking, trustworthy product/SKU metrics and CSV historical imports.

Architecture: Next.js 16 + TypeScript + Tailwind + Recharts + TanStack Table; Django 5.2 LTS + DRF + PostgreSQL 17; Celery + Redis; Docker Compose + Caddy; pytest, Playwright, k6 planned. API under `/api/v1`, same-origin sessions and CSRF, exact decimal money and UTC timestamps.

Project Windows path: `D:\Shadman-Desktop\Career\productstat`.

WSL path: `/mnt/d/Shadman-Desktop/Career/productstat`.

The sibling `student-erp` project was read for conventions and its existing processes were left running and unchanged.

## Environment established

- Ubuntu WSL1, Python 3.12, kernel `4.4.0-19041-Microsoft`.
- Dedicated runtime: `/home/shadman/.local/share/productstat`.
- Python venv: runtime `/.venv`; dependencies installed, frozen in `backend/requirements.lock.txt`.
- PostgreSQL 17.12 installed from official PGDG repository. Signing key fingerprint verified in `scripts/install-system.sh`. User-owned cluster: runtime `/pgdata`, localhost port **55433**, database/user `productstat`.
- Redis installed; ProductStat instance used localhost **56379**, runtime persistence preserved.
- Local `.env` generated with random secrets; ignored by Git. Never print its secrets into reports. Django supports the root scripts' `DJANGO_*`, `PG*`, `PUBLIC_APP_URL` aliases.
- Node 24 was downloaded and checksum verified but its ELF binary is rejected by WSL1's kernel (`Exec format error`); it runs through the ELF loader but this is unsuitable for child-process tooling. Separate Node **22.23.5 LTS** runtime copied from the already installed portable runtime to `~/.local/share/productstat/node22`. `scripts/env.sh` selects it on WSL1; Next16 supports it. Dockerfile selects Node24 for modern Linux.
- Frontend npm installation completed and `frontend/package-lock.json` exists (95 initial packages).
- Windows Node is available through `Get-Command node`: Codex bundled runtime. Windows Playwright Chromium and FFmpeg downloads completed; headless-shell download was interrupted at roughly 40% when stopped. No browser was launched or UI test run.

## Implemented code (not all integrated or verified)

### Backend commerce

`backend/config`, `backend/commerce/models.py`, `services.py`, `payments.py`, `views.py`, `urls.py`, serializers, permissions, CSRF middleware, and `schema.py` exist.

Models include CompanySettings, DeliveryZone, User, Product, SKU, Order, OrderLine, Shipment/ShipmentLine, Payment, ReturnRequest/ReturnLine, Refund/RefundLine, StockMovement, AuditEvent, ImportBatch and OutboxEvent.

Implemented transactional stock reservation/dispatch/cancellation, COD collection versus settlement, returns/inspection/restock/refund recording, guest order tokens, checkout idempotency bound to identity and payload, customer accounts, catalogue/cart, staff catalogue/stock/order/return/refund/user/settings/audit APIs, gateway initiation/server callback validation, reservation expiration, historical-order write protection and backend permissions. Core operations reads were restricted to operators/administrators to avoid analyst access to customer PII.

Initial migration `commerce/migrations/0001_initial.py` was generated and applied to the dedicated database. Subsequent model changes, if any, must be checked on resume; do not assume schema matches the latest files.

### Reporting, imports, jobs and seed

`commerce/reporting.py`, `reporting_views.py`, `reporting_urls.py`, `imports.py`, `import_views.py`, `import_urls.py`, `tasks.py`, and management command `seed_demo.py` exist.

Reporting includes activity measures, delivery-cohort return rates with FIFO allocation, comparison/trends, redacted drilldowns and matching CSV, terminal delivery outcomes and company-wide collection/settlement measures. Imports include staged preview/validation/commit, duplicate protection, related-file historical batches and Celery execution. Outbox and expiry tasks exist.

Root ran the full seed successfully on the real dedicated PostgreSQL database:

| Entity | Count |
|---|---:|
| SKUs | 2,000 |
| Orders | 25,000 |
| Order lines | 75,000 |
| Shipments | 23,706 |
| Shipment lines | 71,118 |
| Payments | 21,416 |
| Return requests / return lines | 4,102 each |
| Refunds / refund lines | 4,102 each |

Synthetic history spans 365 days. Seeding is guarded against resetting existing business stock/history. Do not rerun with a different scale against this database. Repeated-seed idempotency was not independently verified yet.

Local development accounts: `administrator`, `operator`, `analyst`, `customer`; password `ProductStatDemo!2026`. These are local demo credentials, not deployment credentials. DEBUG=0 seeding requires separate explicit strong administrator and viewer passwords and refuses the development default.

### Frontend

Configuration, API client, app layout/catch-all route, shared shell/UI components, storefront/product/cart/checkout/account/tracking/return components, staff product/inventory/order/return/refund/team/settings components, analytics and imports components exist.

**Missing at stop:** `src/app/globals.css` is imported but absent; `public/products/*.svg` assets absent. No frontend build/typecheck or browser verification completed.

### Root infrastructure and scripts

Created `.gitignore`, `.gitattributes`, `.dockerignore`, `compose.yaml`, backend/frontend Dockerfiles, `deploy/Caddyfile`, `.env.production.example`, Windows `Start-ProductStat.ps1`, setup/env/database/migration/seed/dev/check/schema/run scripts, encrypted logical backup and isolated restore-verification scripts, and draft systemd backup units.

These infrastructure files are **draft/unverified**. Docker is not installed in this WSL environment. No images built, deployment performed, remote publication made, backup/restore exercise completed, README written, CI workflow created or k6 run completed. No Git commit/push or hosted service creation was performed.

## Verification completed before stopping

- **Root directly verified:** `tests/test_contention.py`: 2 passed in 4.34s. Fifty independent concurrent checkout attempts against five units produced five orders and 45 validation rejections; twelve same-key retries created one order and reservation.
- **Core agent reported:** Django check clean, no migration drift and `tests/test_core.py`: 15 passed in 10.94s **before** its latest schema/view refactor. Coverage included anonymous CSRF, secure-token IDOR, analyst PII denial, repeat checkout after cart clear, partial cancellation and COD fulfilment/collection/settlement, partial return/refund limits, immutable history, gateway failure/mismatch/late-capture/replay and bounded order-list queries.
- **Reporting agent reported:** Django check/compilation clean and 8 reporting/import tests passed using separate `test_productstat_reporting` DB. Delivery-cohort and cash logic covered. Latest code requires a combined regression run.
- **Reporting agent measured:** one full-data analytics call took **2.489 seconds**, above the chosen two-second target. This is not a load-test pass.
- No complete combined suite, UI test, accessibility review, production settings validation, load/concurrency browser test, recovery exercise or external gateway sandbox transaction completed.

## Known blockers and unfinished work — resume here

1. **Fix OpenAPI schema blocker:** `commerce/schema.py` class `Company(SettingsSerializer)` declares `delivery_zones` but inherits a `Meta.fields` list omitting it. `manage.py spectacular` fails. Latest core schema annotations and list/detail route refactor are otherwise written but unverified; rerun core tests after repair. Reporting/import schema warnings also remain. Generated frontend API definitions and `openapi-typescript` dependency are pending.
2. **Finish frontend before attempting normal start:** create the stylesheet and SVG art (`tote.svg`, `headphones.svg`, `lamp.svg`, `bottle.svg`, `watch.svg`, `chair.svg`; coordinate actual seed filenames). Change npm scripts to `next dev --webpack ...` and `next build --webpack`. Current Turbopack fails on mounted D: under WSL1 with cache fsync `Invalid argument (os error 22)`. Requested webpack change had NOT been applied at stop.
3. **Resolve frontend API mismatches:** order `total` -> backend `grand_total`; singular `shipment.status` -> `shipments[]` with `state`; analytics `.delivery` and `.cash` payloads; multipart related-file imports; catalogue pagination/server-side staff search. Product editor submits Bangla fields not documented/supported by current model contract. Avoid silent zero-value fallbacks masking contract errors. Customer return UI currently relies on old singular shipment shape and needs correction.
4. **Historical related-event grouping bug:** related CSV import currently creates separate shipments/returns/refunds per contributing line instead of grouping shared external event IDs. This inflates terminal shipment statistics. Add shared event grouping and tests. Validate duplicate `source_payment_id` and consistent same-order metadata across related rows.
5. **Task recovery:** outbox retries may immediately exhaust five attempts in one dispatcher invocation; implement backoff/recovery and tests. Verify interrupted imports/worker restarts cannot duplicate effects. Atomic import commit means progress appears mainly at transaction boundaries.
6. **Core planned features not implemented:** configurable tax rate, immutable line tax snapshots and proportional tax refunds; preparation stage/action. Root requested these immediately before user stop; no edits begun. Additional numeric DB constraints, public-demo external-email suppression and sandbox-versus-real-company fulfilment safeguard remain pending.
7. **Documentation drift:** `docs/API_REPORTING.md` still describes the old order-cohort response; actual code and `METRICS.md` use delivery cohorts. Update cash/delivery payload documentation. Review `API_CORE.md` against latest route refactor. Root README, architecture diagram, full implementation status, test evidence and portfolio case study remain unwritten.
8. **Infrastructure gaps:** backup scripts/timer, Compose health redirects/readiness and all production settings need testing. Current backup timer draft assumes host-accessible PG/runtime despite Compose DB being private; make it actually compatible with the chosen deployment. Media restore/content verification needs review. No recovery claim yet.
9. **Finish meaningful integration verification:** combined pytest/migration/schema checks; frontend build; complete customer purchase -> staff dispatch/delivery/COD settlement -> partial return/refund -> report reconciliation; authorization; duplicate import proof; full-dataset analytics optimization and measured load; encrypted backup/restore; CI and k6 scripts.
10. **External release prerequisites:** real SSLCOMMERZ sandbox credentials absent; SMTP/hosting/domain/off-server backup destination absent. Keep gateway truthfully unavailable rather than simulated paid. Live payments remain disabled until separate validation. Public demo must not expose known writable administrator credentials.

## Process state at checkpoint

Root stopped its backend (port 8001), terminated its Celery worker, stopped PostgreSQL17 cluster on 55433 cleanly and issued Redis56379 `shutdown save`. Frontend3000 had already exited from the Turbopack error. Playwright download was interrupted. No implementation agents remain active. Existing Campus ERP backend8000/frontend5173/PostgreSQL16 port55432 were deliberately preserved.

## Resume commands (only after a new user instruction)

From PowerShell, pass script paths directly to WSL to avoid nested Windows/Bash `$variable` quoting problems:

```powershell
wsl.exe -d Ubuntu -- bash /mnt/d/Shadman-Desktop/Career/productstat/scripts/database.sh
wsl.exe -d Ubuntu -- bash /mnt/d/Shadman-Desktop/Career/productstat/scripts/test-backend.sh
```

Read this checkpoint and the current contracts first, repair the listed blockers, then verify migration drift. Do not assume `check.sh` or `dev.sh` passes yet. After fixes, the intended command is:

```powershell
wsl.exe -d Ubuntu -- bash /mnt/d/Shadman-Desktop/Career/productstat/scripts/dev.sh
```

Intended app URL: `http://localhost:3000`; backend: `http://localhost:8001/api/v1/`.

Do not start a new project, reseed/reset the existing database, overwrite sibling work, deploy/publish, or claim completion merely because this checkpoint exists.
