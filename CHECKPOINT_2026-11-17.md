# Historical ProductStat checkpoint — 17 November 2026

**Superseded:** the user explicitly resumed after this checkpoint. The remaining implementation and local verification are recorded in [the release status](docs/RELEASE_STATUS.md) and [validation evidence](docs/VALIDATION.md). The stop instructions below are preserved as historical context, not the current work status.

**Latest instruction: stop.** Saved at approximately **12:25 Asia/Dhaka** after a renewed explicit stop request. Do not resume implementation, tests, deployment or scheduling without a new user instruction. The earlier Continue at12:05 is superseded by this later stop.

## Latest state at the stop

- All agents were interrupted. No ProductStat application, frontend build, pytest or profiling processes were observed after cleanup. PostgreSQL/Redis persistence and the sibling student-erp project were left unchanged.
- This snapshot is unfinished work, not a verified release. Save it on `checkpoint/2026-11-17-paused-hardening`, keeping main's earlier verified source separate. Use a `[skip ci]` checkpoint commit so saving does not start another test run after the stop request.
- Model migrations0005 and0006 are applied to the preserved local database: import fingerprints, nullable historical order/dispatch dates, import settlement dates, current historical revisions and protected supersedes links. Live orders still require dates and remain current. No reset was performed.
- Core/monitoring focused suite:44 passed in28.76seconds before root's additional calendar-day return test. Reporting focused suite:26 passed before the later performance edit. Import agent confirmed28 passing focused tests in10.43seconds; strict OpenAPI with fail-on-warning, Django checks and migration consistency also completed successfully before the stop.
- Frontend types and formatting passed. The latest optimized build compiled and completed TypeScript/static generation, but was stopped during trace collection. **Do not claim that latest build completed.** The earlier build and four browser tests passed before the newest hardening changes; the new five-test browser suite has not run.
- Two-minute k6: **2,452 requests, zero errors**. Catalogue p95 **513.79ms**, passes1000ms target. Analytics p95 **2348.54ms**, fails2000ms target. Do not replace this failure with the older passing30-second result. Private raw summary is `.runtime/k6-summary-before-query-tuning.json`; `.runtime/k6-summary.json` also holds that failed candidate run.
- Profiling before optimization: default report2.149s, full-year2.544s; activity query uses an external merge spilling about10.6MB to disk over147,465 event rows. Evidence/scripts: `.runtime/report-profile-before.json`, `.runtime/profile_reporting.py`. They are private runtime artifacts, not published evidence yet.
- **Untested change in reporting.py:** removed DISTINCT order counting from the large activity GROUPING SETS query and added a separate creation-only order-count query. No test/profile/benchmark has run afterward. Cohort and coverage optimizations have not been implemented. Cache TTL remains30seconds and wait remains1.8seconds; premature fallback can duplicate cold computations.
- **Required pending privacy fix:** return-reason reports currently emit raw free text. Normalize only known reason categories and map unrecognized free text to Other/unspecified before exposing it to analysts. Preserve the original staff record. Add a regression with a private name/phone. Do not expose raw free-text reasons through analytical CSV/drilldowns.
- **Required pending coverage fix:** unknown refund dates are accepted by the new importer, but coverage.undated_refund_amount is not yet implemented. The frontend row is already wired and will show a dash until the backend/schema support it.
- Administrator correction API/UI is written: preview before/after totals, reason and expected old revision; durable commit creates a linked current revision and keeps old financial/event records. Final combined and browser verification is still required. The five-test Playwright suite adds this journey, pending execution.
- **Known import race to fix first:** correction preview/prepare currently permits queued/validating batches. A validator's stale final save could overwrite an approved/completed correction. Restrict correction approval and preview.can_correct to ready/failed batches, then add a regression for the validation-state guard. This bug was identified after the passing import tests and deliberately left unchanged at the stop.
- Root fixed live return eligibility to use Dhaka calendar-day boundaries and added an unrun final-day/next-day test. Reporting's calendar-day alignment passed the earlier focused suite.
- Full recovery5.45s passed before0005/0006; repeat after final schema changes. Actual asynchronous import/restart evidence predates new fingerprint/revision code and should be rerun when resuming.
- Caddy container health now checks its internal loopback admin endpoint rather than assuming a production domain certificate covers localhost. New Compose change needs the next actual container CI run.

## Next actions after an explicit resume

1. Read this entire checkpoint and live git status; keep the preserved database. Review/test the unverified report order-count edit.
2. Finish the reason-category privacy and undated-refund coverage fixes. Optimize actual cohort/coverage bottlenecks and bounded cache stampede handling without altering the acceptance workload or TTL to disguise failures.
3. Complete strict OpenAPI/client regeneration, the combined backend suite and a fresh optimized frontend build. Run all five Playwright journeys with a real worker; CI now starts its browser worker after the separate restart test to avoid interference.
4. Run two-minute k6 alone, with no concurrent builds/tests, until the unchanged targets are met or report the remaining performance gap honestly. Repeat asynchronous worker verification and encrypted recovery for the final candidate.
5. Publish only allowlisted synthetic evidence, finalize validation docs, scan staged paths/secrets, commit/push the tested candidate and verify the exact HEAD in CI. Public hosting, SMTP, merchant payments and off-server backup delivery remain separate external gates.

The latest estimate given was **about15–20% of local v1 remaining**, approximately **2–4 more hours of active assistant work**, subject to regression findings. It is a rough estimate, not a guarantee. No work is scheduled to continue automatically.

## Earlier 12:05 snapshot (historical context)

The following details describe the earlier checkpoint. Where they conflict with the latest stop state above, use the latest state.

## Repository and preference

- Project: `D:\Shadman-Desktop\Career\productstat`, developed through Ubuntu WSL at `/mnt/d/Shadman-Desktop/Career/productstat`.
- Public repository, explicitly authorized: <https://github.com/Shadman-Al-Muksit/productstat-commerce>.
- Last pushed commit: `3bd432a82dfc915d6be4a5d423c368f6897b0011`.
- Both GitHub Actions jobs passed at that commit: <https://github.com/Shadman-Al-Muksit/productstat-commerce/actions/runs/44015893889>.
- The user's default is to create a GitHub repository per project, ask public/private before publishing, and record progress through commits/pushes. Their explicit memory update was saved separately in the authorized ad-hoc memory notes folder.

## Verified baseline

- Storefront, EN/BN navigation, cart, guest/account checkout, private tracking, staff catalogue/stock/order/return/refund/settings workflows, analytical reports and imports are implemented.
- CI at the pushed commit: 70 backend tests and four Playwright tests passed; types, formatting, production build, strict OpenAPI and actual Celery checks passed.
- All three Docker images built. Compose/Caddy HTTPS runtime, standalone storefront assets/metadata, COD purchase → delivery → partial return → refund/report reconciliation, and encrypted private-volume/database restoration passed in disposable CI.
- Larger local synthetic fixture: 2,000 SKUs, 25,000 historical orders, 75,000 historical lines, plus a few synthetic integration orders.
- Latest local combined run before subsequent hardening: 72 backend tests passed in 35.43 seconds; schema/types/format/build passed.
- Latest local encrypted recovery: matching database totals including 18,845 settlement events, four private files, 5.45 seconds. It restored 25,005 orders and 75,005 lines into an isolated database, then removed only that restore target.
- Earlier final-style 30-second k6: 684 successful requests, catalogue p95 429 ms, analytics p95 100 ms. Initial uncached baseline failed latency targets. **A final two-minute run remains pending.**
- The optimized local preview launcher was started, checked for HTTP200/API health, duplicate-port refusal and Ctrl+C cleanup. Its owned backend/frontend/Celery groups were stopped. PostgreSQL/Redis persistence remains running. No application or test processes were observed at checkpoint time.

## Uncommitted work and unresolved checks

Run `git status --short` before resuming; there are substantial uncommitted source/docs/screenshots changes. They have not received final integration verification and must not be described as the verified release.

1. **Reporting contract correction:** net delivered value must subtract accepted returned merchandise at inspection, independently of cash refund completion. Add returned_value, dated cancellation release events/drilldown, unresolved cohort cases, SKU breakdown, return-reason grouping, company-wide full cash refunds, and numerical coverage for unknown historical dates. Frontend components and regression journeys are partly wired. Reporting agent owns backend reporting files/tests/docs.
2. **Operational monitoring:** a read-only IsOperator endpoint `/api/v1/staff/operations-health/`, operations_check command, five-minute systemd examples, 48-hour COD review flags, exhausted-job/import/payment-exception counts and shared Redis throttle storage have been written. Final test results need inspection. Root wired the staff overview. These checks do not send external alerts; alert routing still needs deployment configuration.
3. **Import exactness and missing dates:** canonical fingerprints distinguish exact repeated source IDs from conflicting changed records. Model migration0005 adds Order/StockMovement import_fingerprint fields and was applied without reset. Import agent is implementing validation/commit checks. Unknown historical dates must stay NULL, with coverage; additional model/schema migration is pending.
4. **Administrator historical corrections:** agreed design retains old immutable records, creates a new historical revision linked by Order.supersedes, marks only one source identity is_current=True, and filters reports to the current revision. Administrator review, reason, expected prior revision and audit evidence are required. No implementation of revision support has yet been verified; coordinate model/import/reporting agents before changing migrations.
5. Regenerate strict OpenAPI and frontend types after final model/API changes; format/typecheck/build and run the combined backend/browser suites against the new candidate.
6. Run the final two-minute k6 workload alone, without concurrent builds/tests; repeat encrypted recovery after the final schema changes. Publish only the allowlisted synthetic evidence through scripts/publish-evidence.py.
7. Finalize docs/VALIDATION.md and OPERATIONS.md, scan staged files for private paths/secrets, commit/push, and wait for CI at that exact HEAD to pass.

## Coordination at checkpoint

All three active agents were interrupted when the stop request arrived. Resume through followup tasks after reviewing any tool session results:

- `/root/domain_design`: models/migrations, monitoring endpoint/config/tests, operational/validation docs.
- `/root/delivery_plan`: reporting queries/schema/tests/metric/API docs and integration coordination.
- `/root/delivery_plan/import_conflicts`: imports.py, import views/tests/docs and reviewed historical revisions.
- Root: frontend, launcher scripts, performance/recovery evidence, GitHub/CI and final integration.

Avoid concurrent pytest sessions against the same test database. Do not run load measurements alongside heavy verification. Never reset or reseed the preserved business database to fix schema problems.

## Runtime and restart

- Linux runtime: `/home/shadman/.local/share/productstat`; Python3.12 venv, PostgreSQL17 on55433, Redis on56379, compatible portable Node22 for WSL1. Modern Linux containers use Node24.
- Source local configuration through `scripts/env.sh`; keep `.env`, runtime auth, databases, private uploads, backup keys and encrypted archives out of Git and tool output.
- Restart development with `bash scripts/dev.sh`; optimized preview after a successful build with `bash scripts/dev.sh --preview`.
- Windows Playwright Chromium is available; backend/database remain in WSL.
- Leave the sibling student-erp project and its PostgreSQL16 instance unchanged.

## Estimate given to the user

Approximately 80–85% of the local first release is complete, with 15–20% remaining. Estimated remaining engineering effort: 6–10 focused hours, subject to regression findings. This is a rough estimate, not a deadline or acceptance claim.

Public hosting/domain, actual merchant sandbox/live transactions, external SMTP and off-server backup delivery are separate operational gates requiring infrastructure/credentials. No hosted production-readiness claim has been made.
