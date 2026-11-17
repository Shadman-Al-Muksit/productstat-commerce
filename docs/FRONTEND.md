# ProductStat frontend

The frontend is a Next.js 16 App Router application. Django remains the authority for prices, inventory, order transitions, access control and metric calculations. No catalogue, order or dashboard data is generated in the browser.

## Local development

Use Ubuntu WSL and the project runtime installed by the root setup scripts:

```bash
cd /mnt/d/Shadman-Desktop/Career/productstat
source scripts/env.sh
cd frontend
npm ci
npm run dev
```

The storefront runs at `http://localhost:3000`. API requests under `/api/v1/` are proxied to `API_INTERNAL_URL`, defaulting to `http://127.0.0.1:8001`. Keep `skipTrailingSlashRedirect: true`: Django API URLs intentionally end with a slash, and Next's default normalization otherwise causes a redirect loop.

The npm scripts explicitly select webpack. WSL1 on the mounted Windows workspace cannot reliably use Turbopack's filesystem cache. The setup chooses portable Node 22 LTS on WSL1; the deployment image uses Node 24.

## Interfaces

- `/`: searchable, categorized, sorted and paginated catalogue; persistent English/Bangla browsing preference.
- `/products/<slug>`: variants, authoritative availability and add-to-bag operation. Product metadata is fetched on the server.
- `/cart`, `/checkout`: session cart, quantity changes, delivery zones, tax estimate, COD and hosted SSLCOMMERZ sandbox handoff. Checkout uses an idempotency key and displays genuine gateway configuration failures.
- `/orders/<id>?token=...`, `/track`, `/account`: guest-token or owner-protected order access, registration/login, cancellation and partial return requests.
- `/staff`: operational overview; products/inventory, paginated orders, preparation/dispatch/delivery, COD collection/settlement, returns/inspection, refund evidence, staff access and company settings.
- `/analytics`: date/product filters, comparisons, event-period trends, delivery cohorts, company-wide money measures, redacted drill-downs and matching CSV export.
- `/imports`: validated catalogue/stock/history imports, multiple related historical CSVs, asynchronous progress, row errors, preview and explicit commit.

Workspace navigation and route guards reflect roles, while Django enforces the same restrictions independently. Shared staff demo access must remain read-only. Customer and private workspace routes emit `noindex, nofollow` metadata.

## API contracts

`src/lib/schema.d.ts` is generated from the backend OpenAPI document and committed. Core frontend types are aliases of these generated definitions rather than a second hand-written schema. Regenerate after an API change:

```bash
bash ../scripts/schema.sh
# or, after docs/openapi.yaml has already been generated:
npm run generate:api
```

The client sends cookie credentials and CSRF tokens for unsafe requests. Financial values remain decimal strings in API contracts; frontend arithmetic is limited to the clearly provisional checkout display estimate. The server recalculates the final order totals. Missing money fields render as an em dash rather than a misleading zero.

Analytics money measures are company-wide when the backend says a product filter cannot be applied. Return rates use the backend's delivery cohort and cutoff. Product rows and activity measures follow the selected product/date filters. Do not relabel merchandise value as profit or collected cash.

## Design and verification

The interface uses a neutral, muted retail palette with teal actions, mobile-first storefront layouts and denser staff tables. Product illustrations are original local SVG files; no remote image service is required. Dialogs trap keyboard focus, close on Escape and restore focus to the originating control. Form controls use explicit labels and visible focus states; reduced-motion preferences are respected.

```bash
npm run typecheck
npm run format:check
npm run build
npm run test:e2e
```

The root owns Playwright's configuration and end-to-end evidence. `product-card`, `add-to-cart` and `checkout-submit` test IDs identify the main shopping journey. Build and test outcomes belong in the release evidence; a successful build alone is not proof of production readiness.
