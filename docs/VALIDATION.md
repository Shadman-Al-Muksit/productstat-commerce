# Validation record

The local release candidate is undergoing final integration. Automated application and Docker-runtime verification of the reference commit passed on **17 November 2026**. Reporting, historical-import and operational-monitoring changes after that run require final regression; their combined counts and performance results remain explicitly pending. A public production host has not been provisioned.

The reproducible CI reference is [GitHub Actions run 44015893889](https://github.com/Shadman-Al-Muksit/productstat-commerce/actions/runs/44015893889), commit `3bd432a82dfc915d6be4a5d423c368f6897b0011`. Both jobs completed successfully at 10:17 Asia/Dhaka on 17 November 2026. These results identify the commit actually tested; they do not stand in for verification of subsequent changes.

## Application verification

The [application job](https://github.com/Shadman-Al-Muksit/productstat-commerce/actions/runs/44015893889/job/133813615753) used Ubuntu 24.04, Python 3.12, Node 24, PostgreSQL 17 and Redis 7.

| Check | Recorded result at the reference commit |
|---|---|
| Combined backend suite | **70 passed in 11.41 seconds** |
| Django system checks and migration consistency | Passed |
| OpenAPI validation, generated TypeScript definitions and checked-in contract consistency | Passed |
| Frontend typecheck, formatting and optimized build | Passed |
| Real Celery worker/import verification with eager execution disabled | Passed |
| Playwright browser suite | **4 passed in 10.2 seconds** |

The backend suite covers stock contention, checkout retries and access control, partial cancellation/returns/refunds, payment callback verification, dated settlement increments, reporting reconciliation, imports, cache invalidation and backup extraction checks. Browser coverage includes the English/Bangla storefront, keyboard search and mobile layout; guest checkout through COD collection/settlement, partial return/refund and report reconciliation; analyst access restrictions; and staff order navigation. This is functional coverage, not a complete accessibility or penetration audit.

The asynchronous check uses an actual worker and PostgreSQL-backed pending work. The repeated CSV import must leave stock unchanged, and queued work must survive the worker stop/restart. This ran separately from eager task execution used in unit tests.

**Final release-candidate regression: pending.** The latest reporting corrections and their new assertions will receive a separate combined test run and CI reference before the release record is finalized.

## Container runtime and HTTPS

The [containers job](https://github.com/Shadman-Al-Muksit/productstat-commerce/actions/runs/44015893889/job/133813616258) built all three images, validated Compose/Caddy and started PostgreSQL, Redis, Django/Gunicorn, Celery worker/beat, the Next.js standalone frontend and Caddy.

The disposable environment used `DJANGO_DEBUG=0`, secure session/CSRF cookies, private database/Redis services and Caddy HTTPS with a **localhost CI certificate**. The test certificate bypass was restricted to `https://localhost`; this does not verify a public domain or publicly trusted production certificate.

[Sanitized container smoke evidence](evidence/ci-container-smoke.json) records successful storefront HTML, a bundled JavaScript asset, product SVG and product metadata checks. It also records a synthetic purchase through preparation, dispatch, delivery, COD collection and settlement, partial return inspection/restocking, refund confirmation and refreshed report totals. Guest access without the order token was rejected. The API workflow took **0.56 seconds**; this is one smoke workflow's duration, not a load-test latency result.

The container fixture began with **300 synthetic orders and 80 SKUs**. The smoke purchase increased it to 301 orders and 901 lines. It is separate from the larger local fixture of **2,000 SKUs, 25,000 historical orders and 75,000 lines**, which later integration checks extend with separately identified synthetic operational records.

## Encrypted recovery

The container job backed up its database and private-media volume using a PostgreSQL exported snapshot, an AES256-encrypted GPG archive and a checksum manifest. It decrypted and restored into a newly named isolated database, compared database totals and verified the captured private-file hash. The passing restore database was then removed.

[Sanitized container restore evidence](evidence/ci-container-restore.json) records **matching totals, one verified private file and a 0.26-second verification** for the small container fixture. The restored database contained 301 orders, 901 lines, 80 SKUs and 233 settlement events; settlement event totals matched the payment compatibility balances. This establishes the container network/volume path and recovery procedure for that fixture.

The [final full-fixture local recovery](evidence/restore.json) also passed: **5.45 seconds**, **four verified private files**, **25,005 orders, 75,005 lines and 2,000 SKUs**. Orders, inventory, collections/refunds and settlement checks matched the exported snapshot. The restored settlement ledger contained **18,845 events totaling BDT 476,314,510.00**. The isolated restore database was dropped after verification. The five orders beyond the historical fixture are synthetic integration records.

These measured runs do not prove off-server backup delivery, a production failover or the proposed operational RPO/RTO.

## Performance

The two-minute candidate run on **17 November 2026** completed **2,452 valid requests with zero request errors** against the full local fixture. It used 20 concurrent authenticated customer browsing sessions and five staff reporting sessions, with Gunicorn, PostgreSQL and Redis in the local WSL environment.

| Measure | Recorded p95 | Unchanged target | Result |
|---|---:|---:|---|
| Catalogue API | 513.79 ms | Below 1,000 ms | Pass |
| Analytics API | 2,348.54 ms | Below 2,000 ms | **Fail** |

The candidate therefore **failed the performance acceptance check**, despite its successful response checks. Query profiling/optimization and a fresh two-minute retest are pending. The two-second analytics target has not been relaxed. Final results will identify the retested candidate and retain this failed measurement as the preceding result.

An earlier uncached 25-session run also missed the latency targets. The implementation now uses shared Redis reporting caching with committed-write invalidation, bounded stampede protection, visible calculation timestamps and fresh-database fallback. The candidate measurement above includes that implementation; caching alone did not meet its analytics target. Local WSL results describe the developer environment and do not establish capacity for an unmeasured hosting plan.

## Remaining external release work

The following have **not** been configured or verified: a public application host/domain, external SMTP delivery, a merchant-credential SSLCOMMERZ sandbox transaction, live payment/refund processing, and delivery of backups to an off-server destination. Public source-code publication and disposable CI deployment do not establish these operational outcomes.

The gateway remains explicitly unavailable without credentials. Sandbox payments cannot authorize real-company fulfillment. Refund confirmation records external transaction evidence and does not execute a transfer. Daily backups with a 24-hour RPO and four-hour RTO remain deployment targets until the target server, protected key storage, off-server destination and recovery exercise are demonstrated.
