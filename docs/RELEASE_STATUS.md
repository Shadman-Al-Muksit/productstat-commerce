# ProductStat Commerce release status

20 November 2026 update: the storefront now focuses on electronics with larger typography, teal/navy styling, category browsing, SKU colour imagery and a circular shopping-cart badge. **145 backend tests and six browser journeys passed**; TypeScript, formatting, OpenAPI and the final optimized frontend build passed. The local app uses the optimized preview. [Storefront details](STOREFRONT.md) and [current validation](VALIDATION.md) describe the preservation checks and test environment.

The old mixed catalogue was archived; its transactions, stock and reservation balances remain intact. This does not change the external deployment/payment/backup prerequisites below.

## Initial release record

17 November 2026. The earlier paused checkpoints are historical; the user explicitly resumed implementation and authorized final verification and publication.

## Implemented first release

- English/Bangla storefront, SKU catalogue, cart, guest/account checkout and private order tracking.
- Atomic stock reservation, COD fulfilment, separate collection/settlement records, partial cancellation and returns, inspection and verified refund recording.
- SSLCOMMERZ hosted sandbox adapter with server-side validation and duplicate/late callback handling; an actual merchant transaction remains an external gate.
- Product/SKU comparisons, event trends, delivery cohorts, accepted-return merchandise values, separate cash measures, redacted drill-downs/CSV and explicit missing-date coverage.
- Validated asynchronous imports, exact-repeat protection, conflict rejection and administrator-reviewed historical revisions that preserve old evidence without changing live stock.
- Backend roles/CSRF, shared rate limits, audit events, operational checks, deployment configuration, encrypted backup/restoration and automated CI.

## Final verification

| Check | Result |
|---|---|
| Combined backend suite | 136 passed |
| Production frontend, TypeScript, formatting and strict API contract | Passed |
| Playwright desktop/mobile and correction journeys | Five passed |
| Actual worker restart/repeat-import recovery | Passed |
| Two-minute 20-customer/five-staff load | 2,767 valid requests, zero errors; catalogue p95 79.22 ms, analytics p95 1,955.61 ms; unchanged targets passed |
| Full encrypted database/private-file restore | Passed in 5.88 seconds; 13 files and all database/revision totals matched |
| Package advisory scans | No known vulnerabilities reported in production JavaScript or pinned Python dependencies |
| GitHub CI | [Per-commit application/container verification](https://github.com/Shadman-Al-Muksit/productstat-commerce/actions/workflows/verify.yml); artifacts identify the exact tested commit |

The detailed evidence and operating conditions belong in [VALIDATION.md](VALIDATION.md). Public hosting/domain, actual merchant sandbox/live payments, external SMTP and off-server backup delivery require their own configured environment and verification. This local release does not claim those outcomes.
