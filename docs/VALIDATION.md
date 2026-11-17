# Validation record

Local release verification completed on **17 November 2026**. The application uses synthetic data; no public company deployment or actual merchant payment is claimed.

## Functional and security checks

| Check | Final local result |
|---|---|
| Combined PostgreSQL/backend suite | **136 passed in 45.05 seconds** |
| Django system checks and migration consistency | Passed |
| Strict OpenAPI validation and generated TypeScript contract | Passed |
| Frontend typecheck, formatting and optimized standalone build | Passed |
| Playwright purchase, operations, analyst and historical-correction journeys | **Five passed in 39.4 seconds** |
| Actual Celery import/repeat/restart exercise | Passed; stock 46→47→47→46 with audited compensation |
| Production JavaScript dependency advisory scan | No known vulnerabilities reported |
| Pinned Python dependency advisory scan | No known vulnerabilities reported across 43 dependencies |

Backend tests include fifty concurrent checkout attempts against five units, replay-safe checkout/payment callbacks, authorization and CSRF, authenticated-user rate limits, cancellation/expiry/dispatch, tax allocations, partial returns/refunds, individual courier settlements, import conflicts and reviewed revisions. Reporting fixtures verify event dates, delivery cohorts, unresolved cases, missing dates, privacy-safe return categories, cache invalidation/recovery and exact paisa reconciliation across headline, trend, product, SKU, drill-down and CSV.

The browser suite runs against the production frontend and real APIs/workers. It covers English/Bangla navigation, keyboard search and mobile overflow; guest purchase through delivery/COD settlement/partial return/refund; analyst access protection; staff actions; and administrator correction of historical data without changing live stock. Screenshots are in [screenshots](screenshots). This is functional coverage, not a complete accessibility or penetration audit.

Dependency checks found older REST Framework and unused Pillow versions with reported advisories. REST Framework is now pinned to 3.18.2, compatible with the selected Django 5.2 series according to its [project metadata](https://pypi.org/project/djangorestframework/); unused Pillow was removed. [Sanitized audit evidence](evidence/security.json) records the final results. Advisory checks describe their recorded time, not unknown future vulnerabilities. `scripts/security-check.sh` repeats the checks in CI without installing audit tools into the application environment.

## Two-minute API load acceptance

The [final k6 evidence](evidence/load.json) records **2,767 successful requests, zero request errors and all checks passing**.

| Measure | Final p95 | Unchanged target | Result |
|---|---:|---:|---|
| Catalogue API | **79.22 ms** | Below 1,000 ms | Pass |
| Analytics API | **1,955.61 ms** | Below 2,000 ms | Pass |

Conditions: Ubuntu WSL1 on a shared Windows host with **four logical processors and 7.90 GiB physical RAM**; PostgreSQL 17, Redis, four Gunicorn workers with four threads each. Twenty distinct customer identities browse paginated catalogue pages while five distinct analyst identities request reports, with a one-second think time. Every fifth staff iteration requests a full year; the others use the default 30-day report. The fixture contains 2,000 SKUs, 25,000 historical orders and 75,000 historical lines, plus separately identified synthetic integration records. No build, browser test or other verification ran alongside the measured workload. Planner statistics were refreshed after migration using `scripts/analyze.sh`; business data was preserved.

The shared report cache retains its **30-second TTL**, committed-write invalidation and original visible calculation timestamp. Cold requests remain included: maximum observed catalogue latency was 978.18 ms and analytics latency 4,079.58 ms. The analytics p95 margin is 44.39 ms on this short shared-host run. This is not a claim that every report finishes within two seconds, or a production capacity guarantee; remeasure the configured hosting environment before a company pilot.

Earlier candidates are retained: [2,452-request candidate](evidence/load-before-query-tuning.json) missed analytics p95 at 2,348.54 ms; [2,770-request candidate](evidence/load-intermediate-miss.json) missed at 2,067.75 ms. An [initial uncached baseline](evidence/load-before-cache.json) also failed. The older first candidate shared two identities across 25 virtual users; the final harness uses 25 independent identities. These are separate candidate measurements, not an isolated causal comparison. No acceptance thresholds were relaxed.

Optimizations retain the same metric results: creation-only distinct order counts, shared event facts and cumulative paisa allocation, fewer repeated joins/scans, coalesced cache readers and one conditional receipt aggregate. The latter reduced paired real-database cash calculations from 174–245 ms to 133–147 ms with identical results. A slower experimental coverage rewrite was rejected.

## Encrypted recovery and import resilience

The [final full-fixture restore](evidence/restore.json) passed in **5.88 seconds** with **13 private files**. The captured snapshot contained 25,016 orders, 75,016 lines, 2,000 SKUs and 18,848 settlement events. It preserved 25,014 current orders, two superseded orders and two revision links. Order/inventory/payment/refund/settlement/revision totals and every private-file checksum matched after restoration into an isolated database, which was then removed.

The archive combines a PostgreSQL custom dump from an exported repeatable-read snapshot with private media and a checksum manifest, encrypted using AES256/GPG with a separately stored key. Neither the key nor archive is published. [Actual-worker evidence](evidence/async-worker.json) demonstrates repeat-import protection and a durable queued import completing after worker restart. [Seed evidence](evidence/seed.json) retains the original unchanged 25,000/75,000/2,000 fixture check.

These results verify the procedure and captured data; they do not establish off-server delivery, complete server failover or the operational 24-hour RPO/four-hour RTO.

## CI and container evidence

[Verify ProductStat](https://github.com/Shadman-Al-Muksit/productstat-commerce/actions/workflows/verify.yml) repeats the backend suite, strict generated contract, production frontend build, dependency scans, actual worker checks and five browser journeys on Ubuntu 24.04/Python 3.12/Node 24/PostgreSQL 17/Redis 7. Each application artifact includes JUnit results, screenshots, advisory results and `ci-provenance.json` identifying its exact commit/run. Use the run at the final source commit for release status.

The separate container job builds backend/frontend/backup images; validates and starts Compose/Caddy; checks Django deployment settings; exercises HTTPS storefront assets/metadata and the COD→return/refund/report workflow; and restores an encrypted database/private-volume backup. Its localhost self-signed certificate bypass is restricted to disposable CI and does not validate a public domain.

The retained [earlier container smoke](evidence/ci-container-smoke.json) and [restore](evidence/ci-container-restore.json) identify successful run [44015893889](https://github.com/Shadman-Al-Muksit/productstat-commerce/actions/runs/44015893889), commit `3bd432a82dfc915d6be4a5d423c368f6897b0011`, with a 300-order/80-SKU starting fixture. They remain historical reference evidence. Current container artifacts are attached to each current workflow run rather than rewriting the earlier record.

## External release gates

Public application hosting/domain, actual SSLCOMMERZ merchant sandbox/live transactions, external SMTP and off-server backup delivery have **not** been configured or verified. The gateway reports unavailable without credentials; sandbox funds cannot authorize real-company fulfilment. Refund confirmation records external evidence and does not execute a transfer.

Configure company shipping/tax/return settings and private credentials, connect monitoring/backup destinations, restore on the target server and validate its workload before a COD pilot. Merchant onboarding and controlled transaction/refund reconciliation remain prerequisites for live online collection.
