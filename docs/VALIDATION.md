# Validation record

Status on 17 November 2026: implementation is in final integration verification. The public repository records work in progress; it is not a hosted production release.

## Verified so far

- Preserved synthetic fixture: 2,000 SKUs, 25,000 historical orders, 75,000 lines; later integration checks add separate synthetic operational records.
- Core backend: 30 focused tests passed; reporting/imports/cache: 30 focused tests passed; PostgreSQL contention: two tests passed. A final combined run remains pending.
- OpenAPI validation and generated TypeScript definitions passed. Frontend production build and typecheck passed before the latest integration fixes; final build remains pending.
- Browser checks passed for the bilingual/mobile storefront and complete guest purchase, fulfilment, COD collection/settlement, partial return, refund and report reconciliation. Analyst access protection passed separately. Final combined browser run and staff drawer verification remain pending.
- Actual Celery verification: stock46→47 on first CSV, unchanged47 on identical repeat, then restored46 by audited compensation after worker restart. Pending work survived the shutdown; both owned workers exited cleanly.
- Encrypted backup restored into an isolated database; orders, lines, stock, payment/refund totals and private-file checksums matched. Restore verification took4.63seconds for the first full fixture backup.
- Repeating the seed left order, line, stock and money totals unchanged.

## Performance

The initial uncached 25-session k6 run returned successful responses but missed the latency targets. Shared Redis reporting caching was added with committed-write invalidation, bounded stampede protection, visible calculation timestamps and database fallback. Final measured results will replace this provisional section after verification.

## External release prerequisites

No hosted site, container-runtime smoke test, external SMTP delivery, merchant sandbox transaction, live payment or off-server backup delivery has been verified. These require the target infrastructure and credentials. The application must report an unconfigured gateway truthfully and keep sandbox transactions away from real-company fulfilment.
