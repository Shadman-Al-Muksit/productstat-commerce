# ProductStat Commerce

A Bangladesh e-commerce platform connecting a customer storefront, staff operations and auditable product analytics. Built for one company, BDT and domestic physical-goods delivery.

The useful question is not only “what sold?” A manager can follow a product from ordered units to delivery outcomes, accepted returns and confirmed money movements, then inspect the contributing records.

## Run locally

Development and backend verification use Ubuntu WSL. Source files remain on the Windows D: drive; database files and dependencies live in the separate Linux runtime `~/.local/share/productstat`.

```bash
cd /mnt/d/Shadman-Desktop/Career/productstat
# First installation only, if PostgreSQL17/Redis/Python venv prerequisites are missing:
sudo bash scripts/install-system.sh
bash scripts/setup.sh
bash scripts/seed.sh
bash scripts/dev.sh
```

Open **http://localhost:3000**. On Windows, `Start-ProductStat.ps1` starts the same WSL application. Local API documentation is at **http://localhost:8001/api/v1/docs/**.

`seed_demo` creates 2,000 SKUs, 25,000 historical orders and 75,000 lines across a synthetic year. `--small` creates a smaller fresh-development fixture. Existing seeded history and live stock are not reset by repeated seeding. Never change fixture size by deleting business data.

Local-only demonstration accounts:

| Username | Role |
|---|---|
| `administrator` | Company settings, access, operations and financial confirmations |
| `operator` | Catalogue, stock, fulfilment and returns |
| `analyst` | Redacted reports and exports |
| `customer` | Own orders and account |

Local development password: `ProductStatDemo!2026`. Production seeding refuses this default and requires separate private administrator and viewer passwords. Do not publish the local writable account credentials with a hosted demo.

## Supported workflows

- English/Bangla storefront, catalogue search/filtering, variants, persistent cart, guest checkout and customer accounts.
- Server-validated prices/charges, atomic reservations, replay-safe checkout and private guest order links.
- Staff preparation, dispatch, delivery failures, partial cancellation, COD collection and courier settlement.
- Partial returns, receipt/inspection, stock disposition, refund obligations and verified refund recording.
- Typed REST API, backend role permissions, session/CSRF protection, audit events and redacted request logs.
- Activity reports, delivery-cohort return rates, product comparisons, event drilldowns and matching CSV exports.
- Validated catalogue/inventory/historical CSV batches, durable queued work and repeat-import protection.

COD works locally. **SSLCOMMERZ requires real sandbox merchant credentials** in the ignored `.env`; absent credentials produce an explicit unavailable response. A browser success redirect never proves payment. Sandbox money cannot authorize real-company fulfilment. Refund confirmation records external evidence; it does not pretend to execute a gateway transfer.

## Architecture

Next.js16/TypeScript → Django5.2/DRF → PostgreSQL17, with Celery/Redis background work. Django owns business rules and reporting calculations. UI figures, drilldowns and exports share the reporting services.

The local WSL1 kernel needs Node22 LTS and Next's webpack mode; modern Linux deployment images use Node24. The setup scripts select the compatible runtime without replacing other projects' dependencies.

See [architecture](docs/ARCHITECTURE.md), [core API](docs/API_CORE.md), [reporting API](docs/API_REPORTING.md), [metric definitions](docs/METRICS.md), [import schemas](docs/IMPORTS.md), [OpenAPI](docs/openapi.yaml) and [operational runbook](docs/OPERATIONS.md).

## Verification

```bash
bash scripts/check.sh                 # Backend checks/tests + TypeScript + production build
bash scripts/schema.sh                # Validate OpenAPI and regenerate TypeScript definitions
bash scripts/seed-check.sh             # Before/after proof that reseeding does not change data
bash scripts/recovery-test.sh         # Encrypted backup and isolated database/media restore
python3 scripts/install-validation-tools.py
bash scripts/load-test.sh             # 20 browsing sessions + five staff sessions, local k6
```

With the application running, execute `npm run test:e2e` from `frontend`. On this WSL1 machine, use Windows Node with the installed Windows Playwright Chromium; the application/database still run in WSL. Set `PLAYWRIGHT_EXECUTABLE_PATH` if a browser location must be supplied.

Verification results, environment limits and release prerequisites belong in [the validation record](docs/VALIDATION.md). A successful local demonstration is not evidence of a hosted production deployment.

## Deployment boundary

The Docker Compose/Caddy configuration targets a single Ubuntu server, private database/Redis networks, persistent media and an encrypted-backup maintenance container. It is not a marketplace, international-commerce engine or accounting ledger. One shipment per live order is supported; historical related files retain shared external shipment identities.

Deployment requires a domain/server, unique secrets, SMTP configuration when real notifications are enabled, a separately protected backup key and an off-server backup destination. Live online payment collection remains a separate release gate after merchant onboarding and transaction/refund reconciliation.
